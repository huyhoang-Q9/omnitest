"""Thực thi một test run: đọc định nghĩa đã chụp lại, gọi adapter, lưu kết quả từng bước và bằng chứng.

An toàn:
- Worker chỉ chạy định nghĩa khai báo qua adapter; không exec/eval nội dung người dùng. Script code (nếu được
  bật) chỉ chạy trong container sandbox Docker cô lập, không bao giờ trong tiến trình worker.
- Secret chỉ được giải mã trong bộ nhớ của lần chạy, mọi log và chi tiết đều đã che.
- Test có side effect không bao giờ tự retry.
- Hủy: kiểm tra cờ cancel_requested giữa các bước; timeout cho từng test case.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from omnitest_adapters.core.base import AdapterRegistry, ExecutionContext
from omnitest_adapters.core.definitions import TestDefinition
from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.core.results import AdapterResult, ArtifactFile, Outcome, StepOutcome
from omnitest_adapters.core.templating import Variables
from omnitest_adapters.registry import default_registry
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from omnitest_api.config import Settings, get_settings
from omnitest_api.models import (
    FINAL_RUN_STATUSES,
    Artifact,
    Environment,
    EnvironmentVariable,
    Project,
    RunStatus,
    StepResult,
    TestRun,
    TestRunItem,
)
from omnitest_api.security.crypto import SecretCipher

log = logging.getLogger("omnitest.worker")
DEFINITION: TypeAdapter[Any] = TypeAdapter(TestDefinition)
# Lỗi không có ý nghĩa khi thử lại.
NO_RETRY_ERRORS = {
    "blocked_target",
    "not_supported",
    "missing_variable",
    "cancelled",
    "browser_unavailable",
    "invalid_definition",
    "no_steps",
    "appium_unavailable",
    "appium_session",
    "sandbox_disabled",
    "script_disabled",
    "sandbox_unavailable",
    "sandbox_oom",
    "sandbox_output_limit",
    "no_tests",
}
COUNTER = {
    RunStatus.PASSED: "passed",
    RunStatus.FAILED: "failed",
    RunStatus.SKIPPED: "skipped",
    RunStatus.BLOCKED: "blocked",
    RunStatus.ERROR: "errored",
    RunStatus.CANCELLED: "cancelled",
}


def now() -> datetime:
    return datetime.now(UTC)


def final_run_status(statuses: list[RunStatus], cancel_requested: bool) -> RunStatus:
    if cancel_requested and RunStatus.CANCELLED in statuses:
        return RunStatus.CANCELLED
    if any(s in (RunStatus.FAILED, RunStatus.ERROR) for s in statuses):
        return RunStatus.FAILED
    if any(s == RunStatus.BLOCKED for s in statuses):
        return RunStatus.BLOCKED
    if statuses and all(s == RunStatus.SKIPPED for s in statuses):
        return RunStatus.SKIPPED
    if statuses and all(s == RunStatus.PASSED for s in statuses):
        return RunStatus.PASSED
    return RunStatus.FAILED


class RunExecutor:
    def __init__(
        self,
        engine: AsyncEngine,
        settings: Settings | None = None,
        registry: AdapterRegistry | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.registry = registry or default_registry()
        self.cipher = SecretCipher(self.settings.master_key.get_secret_value())

    # ---------- tiện ích DB ----------

    async def _cancel_requested(self, run_id: uuid.UUID) -> bool:
        async with self.sessions() as db:
            return bool(
                await db.scalar(select(TestRun.cancel_requested).where(TestRun.id == run_id))
            )

    async def _heartbeat(self, db: AsyncSession, run_id: uuid.UUID) -> None:
        await db.execute(update(TestRun).where(TestRun.id == run_id).values(heartbeat_at=now()))

    async def _load_variables(self, db: AsyncSession, env: Environment) -> Variables:
        values: dict[str, str] = {}
        secrets: set[str] = set()
        for var in await db.scalars(
            select(EnvironmentVariable).where(EnvironmentVariable.environment_id == env.id)
        ):
            if var.is_secret:
                if var.encrypted_value:
                    values[var.key] = self.cipher.decrypt(var.encrypted_value, f"envvar:{var.id}")
                    secrets.add(var.key)
            elif var.value is not None:
                values[var.key] = var.value
        values.setdefault("BASE_URL", env.base_url)
        return Variables(values, secrets)

    def _save_artifact(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        item_id: uuid.UUID,
        step_id: uuid.UUID | None,
        f: ArtifactFile,
    ) -> None:
        if len(f.data) > self.settings.max_artifact_bytes:
            log.warning("Bỏ qua artifact %s vì vượt giới hạn kích thước", f.filename)
            return
        art_id = uuid.uuid4()
        rel = Path(str(run_id)) / str(item_id) / f"{art_id}-{f.filename}"
        path = self.settings.artifacts_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f.data)
        db.add(
            Artifact(
                id=art_id,
                run_id=run_id,
                run_item_id=item_id,
                step_result_id=step_id,
                kind=f.kind,
                filename=f.filename,
                content_type=f.content_type,
                size=len(f.data),
                sha256=hashlib.sha256(f.data).hexdigest(),
                storage_path=str(rel),
            )
        )

    # ---------- luồng chính ----------

    async def execute_run(self, run_id: uuid.UUID) -> RunStatus | None:
        async with self.sessions() as db:
            run = await db.get(TestRun, run_id)
            if run is None:
                log.warning("Run %s không tồn tại", run_id)
                return None
            if run.status != RunStatus.QUEUED:
                # Job lặp hoặc đã bị hủy trước khi bắt đầu: không làm gì (idempotent).
                return run.status
            run.status = RunStatus.RUNNING
            run.started_at = now()
            run.heartbeat_at = now()
            await db.commit()

            try:
                env = await db.get(Environment, run.environment_id) if run.environment_id else None
                if env is None:
                    raise RuntimeError("Môi trường của lần chạy đã bị xóa")
                variables = await self._load_variables(db, env)
                policy = NetworkPolicy.from_environment(
                    env.base_url, env.allowed_hosts, env.allow_private_network
                )
                project = await db.get(Project, run.project_id)
                # Cờ dự án được đọc lại lúc chạy: Admin tắt script code thì lần chạy đang chờ cũng bị chặn.
                adapter_settings: dict[str, Any] = {
                    "sandbox": self.settings.sandbox_settings(),
                    "script_allowed": bool(project and project.script_enabled),
                }
                items = list(
                    await db.scalars(
                        select(TestRunItem)
                        .where(TestRunItem.run_id == run.id)
                        .order_by(TestRunItem.position)
                    )
                )
                for item in items:
                    if item.status in FINAL_RUN_STATUSES:
                        continue
                    if await self._cancel_requested(run.id):
                        item.status = RunStatus.CANCELLED
                        item.finished_at = now()
                    else:
                        await self._execute_item(
                            db, run, item, env, variables, policy, adapter_settings
                        )
                    setattr(run, COUNTER[item.status], getattr(run, COUNTER[item.status]) + 1)
                    run.heartbeat_at = now()
                    await db.commit()
                await db.refresh(run)
                run.status = final_run_status([i.status for i in items], run.cancel_requested)
            except Exception as exc:
                log.exception("Run %s lỗi hệ thống", run_id)
                await db.rollback()
                run = await db.get(TestRun, run_id)
                assert run is not None
                run.status = RunStatus.ERROR
                run.error = f"Lỗi hệ thống khi chạy: {exc.__class__.__name__}: {str(exc)[:500]}"
                await db.execute(
                    update(TestRunItem)
                    .where(
                        TestRunItem.run_id == run_id,
                        TestRunItem.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                    )
                    .values(
                        status=RunStatus.ERROR,
                        error="Dừng do lỗi hệ thống của lần chạy",
                        finished_at=now(),
                    )
                )
            run.finished_at = now()
            await db.commit()
            return run.status

    async def _execute_item(
        self,
        db: AsyncSession,
        run: TestRun,
        item: TestRunItem,
        env: Environment,
        base_vars: Variables,
        policy: NetworkPolicy,
        adapter_settings: dict[str, Any] | None = None,
    ) -> None:
        item.status = RunStatus.RUNNING
        item.started_at = now()
        await db.commit()
        t0 = time.monotonic()

        try:
            definition = DEFINITION.validate_python(item.definition)
        except ValidationError as exc:
            item.status, item.error, item.error_type = (
                RunStatus.ERROR,
                f"Định nghĩa test không hợp lệ: {exc.errors()[0]['msg']}",
                "invalid_definition",
            )
            item.finished_at, item.duration_ms = now(), 0
            return
        adapter = self.registry.for_kind(definition.kind)
        max_attempts = 1 if item.side_effect else 1 + item.max_retries
        result: AdapterResult | None = None
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            item.attempts = attempt
            await db.commit()
            # Mỗi lần thử dùng bản sao biến riêng: giá trị trích xuất không rò sang test khác.
            variables = base_vars.copy()
            step_rows: dict[int, uuid.UUID] = {}

            async def on_step(
                step: StepOutcome, _attempt: int = attempt, _rows: dict[int, uuid.UUID] = step_rows
            ) -> None:
                row = self._step_row(item.id, _attempt, step)
                _rows[step.index] = row.id
                async with self.sessions() as sdb:
                    sdb.add(row)
                    await self._heartbeat(sdb, run.id)
                    await sdb.commit()

            async def is_cancelled() -> bool:
                return await self._cancel_requested(run.id)

            ctx = ExecutionContext(
                base_url=env.base_url,
                variables=variables,
                policy=policy,
                deadline=time.monotonic() + item.timeout_seconds,
                is_cancelled=is_cancelled,
                on_step=on_step,
                settings=dict(adapter_settings or {}),
            )
            if adapter is None:
                result = AdapterResult(
                    Outcome.BLOCKED,
                    [],
                    f"Không có adapter cho loại test {definition.kind}",
                    "not_supported",
                )
            else:
                try:
                    result = await asyncio.wait_for(
                        adapter.execute(ctx, definition), timeout=item.timeout_seconds
                    )
                except TimeoutError:
                    result = AdapterResult(
                        Outcome.FAILED,
                        [],
                        f"Vượt thời gian tối đa {item.timeout_seconds} giây của test case",
                        "timeout",
                    )
                except Exception as exc:
                    log.exception("Adapter lỗi ở item %s", item.id)
                    result = AdapterResult(
                        Outcome.ERROR,
                        [],
                        variables.mask(f"Adapter lỗi: {exc.__class__.__name__}: {exc}"[:1000]),
                        "adapter_exception",
                    )

            # Lưu bước chưa được ghi qua callback (VD bước bị bỏ qua) và bằng chứng.
            for step in result.steps:
                if step.index not in step_rows:
                    row = self._step_row(item.id, attempt, step)
                    db.add(row)
                    step_rows[step.index] = row.id
            await db.flush()
            for step in result.steps:
                for f in step.artifacts:
                    self._save_artifact(db, run.id, item.id, step_rows.get(step.index), f)
            for f in result.artifacts:
                self._save_artifact(db, run.id, item.id, None, f)
            await db.commit()

            retryable = (
                result.status in (Outcome.FAILED, Outcome.ERROR)
                and (result.error_type or "") not in NO_RETRY_ERRORS
                and not await self._cancel_requested(run.id)
            )
            if not retryable:
                break

        assert result is not None
        item.status = RunStatus(result.status.value)
        item.error = result.error
        item.error_type = result.error_type
        item.finished_at = now()
        item.duration_ms = int((time.monotonic() - t0) * 1000)

    @staticmethod
    def _step_row(item_id: uuid.UUID, attempt: int, step: StepOutcome) -> StepResult:
        return StepResult(
            id=uuid.uuid4(),
            run_item_id=item_id,
            attempt=attempt,
            index=step.index,
            name=step.name[:200],
            status=RunStatus(step.status.value),
            duration_ms=step.duration_ms,
            log=step.log[:200],
            error=step.error,
            details=step.details,
        )

    async def recover_stale_runs(self) -> int:
        """Run 'running' không còn heartbeat (worker chết giữa chừng) được đánh dấu lỗi để không treo mãi."""
        cutoff = now() - timedelta(minutes=self.settings.stale_run_minutes)
        async with self.sessions() as db:
            stale = list(
                await db.scalars(
                    select(TestRun).where(
                        TestRun.status == RunStatus.RUNNING, TestRun.heartbeat_at < cutoff
                    )
                )
            )
            for run in stale:
                run.status = RunStatus.ERROR
                run.error = "Worker dừng bất thường trong khi chạy (mất heartbeat)"
                run.finished_at = now()
                await db.execute(
                    update(TestRunItem)
                    .where(
                        TestRunItem.run_id == run.id,
                        TestRunItem.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                    )
                    .values(
                        status=RunStatus.ERROR, error="Worker dừng bất thường", finished_at=now()
                    )
                )
            await db.commit()
            return len(stale)


async def run_once(run_id: uuid.UUID) -> RunStatus | None:
    """Mỗi job dùng engine riêng: Dramatiq gọi actor trong thread, mỗi lần một event loop mới."""
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        return await RunExecutor(engine).execute_run(run_id)
    finally:
        await engine.dispose()
