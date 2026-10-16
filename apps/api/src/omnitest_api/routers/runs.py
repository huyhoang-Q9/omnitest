import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from omnitest_adapters.core.base import EnvironmentCheck
from omnitest_adapters.registry import default_registry
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api import audit
from omnitest_api.config import get_settings
from omnitest_api.deps import (
    DB,
    CurrentUser,
    ProjectAccess,
    get_project_access,
    require_role,
    require_writable,
)
from omnitest_api.models import (
    FINAL_RUN_STATUSES,
    Artifact,
    Environment,
    Project,
    ProjectMember,
    ProjectRole,
    RunStatus,
    StepResult,
    SuiteItem,
    TestCase,
    TestRun,
    TestRunItem,
    TestSuite,
    TestType,
    User,
)
from omnitest_api.queue import enqueue_run
from omnitest_api.schemas import Page
from omnitest_api.schemas_tests import (
    AdapterOut,
    ArtifactOut,
    RunCreate,
    RunDetailOut,
    RunItemDetailOut,
    RunItemOut,
    RunOut,
    StepResultOut,
)

router = APIRouter(tags=["runs"])
NOT_FOUND = "Không tìm thấy hoặc bạn không có quyền truy cập"


def run_out(run: TestRun, project_key: str | None = None) -> RunOut:
    out = RunOut.model_validate(run)
    if run.started_at and run.finished_at:
        out.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    out.project_key = project_key
    return out


async def run_with_access(
    db: AsyncSession, user: User, run_id: uuid.UUID
) -> tuple[TestRun, ProjectAccess]:
    run = await db.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, NOT_FOUND)
    return run, await get_project_access(db, user, run.project_id)


@router.get("/api/adapters", response_model=list[AdapterOut])
async def list_adapters(_: CurrentUser) -> list[AdapterOut]:
    out = []
    sandbox_on = get_settings().sandbox_enabled
    for a in default_registry().all():
        check = a.check_environment()
        if "script" in a.test_kinds and not sandbox_on:
            check = EnvironmentCheck(False, "Máy chủ chưa bật sandbox chạy script code")
        out.append(
            AdapterOut(
                key=a.key,
                display_name=a.display_name,
                status=a.status.value,
                test_kinds=list(a.test_kinds),
                environment_ok=check.ok,
                message=check.message,
            )
        )
    return out


@router.post("/api/projects/{project_id}/runs", response_model=RunOut, status_code=201)
async def create_run(
    project_id: uuid.UUID, body: RunCreate, user: CurrentUser, request: Request, db: DB
) -> RunOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.TESTER)
    require_writable(access)
    env = await db.get(Environment, body.environment_id)
    if env is None or env.project_id != project_id:
        raise HTTPException(422, "Môi trường không thuộc dự án")

    suite: TestSuite | None = None
    if body.suite_id:
        suite = await db.get(TestSuite, body.suite_id)
        if suite is None or suite.project_id != project_id:
            raise HTTPException(422, "Suite không thuộc dự án")
        ids = list(
            await db.scalars(
                select(SuiteItem.test_case_id)
                .where(SuiteItem.suite_id == suite.id)
                .order_by(SuiteItem.position)
            )
        )
    else:
        ids = list(dict.fromkeys(body.test_case_ids))
    cases_by_id = {
        tc.id: tc
        for tc in await db.scalars(
            select(TestCase).where(
                TestCase.id.in_(ids),
                TestCase.project_id == project_id,
                TestCase.is_deleted.is_(False),
            )
        )
    }
    missing = [i for i in ids if i not in cases_by_id]
    if missing and not suite:
        raise HTTPException(
            422, f"{len(missing)} test case không tồn tại, đã xóa hoặc không thuộc dự án"
        )
    cases = [cases_by_id[i] for i in ids if i in cases_by_id]
    if not cases:
        raise HTTPException(422, "Không có test case nào để chạy")

    reasons: list[str] = []
    if env.requires_run_confirmation:
        reasons.append(
            f"Môi trường {env.name} ({env.kind.value.upper()}) yêu cầu xác nhận trước khi chạy"
        )
    scripts = [tc.code for tc in cases if tc.test_type == TestType.SCRIPT]
    if scripts:
        reasons.append(
            f"{len(scripts)} test script code sẽ chạy trong sandbox Docker: {', '.join(scripts[:10])}"
        )
    side = [tc.code for tc in cases if tc.side_effect]
    if side:
        reasons.append(
            f"{len(side)} test có thể thay đổi dữ liệu trên hệ thống đích: {', '.join(side[:10])}"
        )
    if reasons and not body.confirm:
        raise HTTPException(
            409,
            {
                "code": "confirmation_required",
                "message": "Cần xác nhận trước khi chạy",
                "reasons": reasons,
            },
        )

    title = body.title or (
        f"Suite {suite.name}"
        if suite
        else (cases[0].title if len(cases) == 1 else f"{len(cases)} test case")
    )
    run = TestRun(
        id=uuid.uuid4(),
        project_id=project_id,
        environment_id=env.id,
        environment_name=env.name,
        suite_id=suite.id if suite else None,
        title=title[:300],
        status=RunStatus.QUEUED,
        triggered_by_id=user.id,
        triggered_by_email=user.email,
        total=len(cases),
    )
    db.add(run)
    await db.flush()
    for pos, tc in enumerate(cases):
        db.add(
            TestRunItem(
                run_id=run.id,
                test_case_id=tc.id,
                position=pos,
                code=tc.code,
                title=tc.title,
                test_type=tc.test_type,
                test_case_version=tc.version,
                definition=tc.definition,
                side_effect=tc.side_effect,
                max_retries=tc.retry_count,
                timeout_seconds=tc.timeout_seconds,
                status=RunStatus.QUEUED,
            )
        )
    audit.record(
        db,
        action="run.create",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="run",
        target_id=run.id,
        details={
            "environment": env.name,
            "environment_kind": env.kind.value,
            "count": len(cases),
            "script_count": len(scripts),
            "confirmed": bool(reasons),
        },
    )
    await db.commit()
    await db.refresh(run)
    try:
        enqueue_run(run.id)
    except Exception as exc:
        run.status = RunStatus.ERROR
        run.error = (
            "Không gửi được lần chạy tới hàng đợi (Redis/worker). Kiểm tra dịch vụ và thử lại."
        )
        run.finished_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(503, run.error) from exc
    return run_out(run, access.project.key)


@router.get("/api/projects/{project_id}/runs", response_model=Page[RunOut])
async def list_runs(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    environment_id: uuid.UUID | None = None,
    suite_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[RunOut]:
    access = await get_project_access(db, user, project_id)
    stmt = select(TestRun).where(TestRun.project_id == project_id)
    if run_status:
        stmt = stmt.where(TestRun.status == run_status)
    if environment_id:
        stmt = stmt.where(TestRun.environment_id == environment_id)
    if suite_id:
        stmt = stmt.where(TestRun.suite_id == suite_id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(
        stmt.order_by(TestRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[run_out(r, access.project.key) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/runs/active", response_model=list[RunOut])
async def active_runs(user: CurrentUser, db: DB) -> list[RunOut]:
    stmt = (
        select(TestRun, Project.key)
        .join(Project, Project.id == TestRun.project_id)
        .where(TestRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
    )
    if not user.is_system_admin:
        stmt = stmt.where(
            TestRun.project_id.in_(
                select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
            )
        )
    rows = (await db.execute(stmt.order_by(TestRun.created_at.desc()).limit(100))).all()
    return [run_out(r, key) for r, key in rows]


@router.get("/api/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: uuid.UUID, user: CurrentUser, db: DB) -> RunDetailOut:
    run, access = await run_with_access(db, user, run_id)
    items = await db.scalars(
        select(TestRunItem).where(TestRunItem.run_id == run.id).order_by(TestRunItem.position)
    )
    out = RunDetailOut.model_validate(
        {**run_out(run, access.project.key).model_dump(), "items": []}
    )
    out.items = [RunItemOut.model_validate(i) for i in items]
    return out


@router.get("/api/run-items/{item_id}", response_model=RunItemDetailOut)
async def get_run_item(item_id: uuid.UUID, user: CurrentUser, db: DB) -> RunItemDetailOut:
    item = await db.get(TestRunItem, item_id)
    if item is None:
        raise HTTPException(404, NOT_FOUND)
    await run_with_access(db, user, item.run_id)
    steps = await db.scalars(
        select(StepResult)
        .where(StepResult.run_item_id == item.id)
        .order_by(StepResult.attempt, StepResult.index)
    )
    arts = await db.scalars(
        select(Artifact).where(Artifact.run_item_id == item.id).order_by(Artifact.created_at)
    )
    base = RunItemOut.model_validate(item).model_dump()
    return RunItemDetailOut(
        **base,
        definition=item.definition,
        steps=[StepResultOut.model_validate(s) for s in steps],
        artifacts=[ArtifactOut.model_validate(a) for a in arts],
    )


@router.post("/api/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: uuid.UUID, user: CurrentUser, request: Request, db: DB) -> RunOut:
    run, access = await run_with_access(db, user, run_id)
    require_role(access, ProjectRole.TESTER)
    if run.status in FINAL_RUN_STATUSES:
        raise HTTPException(409, "Lần chạy đã kết thúc")
    now = datetime.now(UTC)
    if run.status == RunStatus.QUEUED:
        # Chưa bắt đầu: hủy ngay. Worker nhận job sau đó sẽ bỏ qua.
        run.status = RunStatus.CANCELLED
        run.finished_at = now
        run.cancelled = run.total
        await db.execute(
            update(TestRunItem)
            .where(TestRunItem.run_id == run.id)
            .values(status=RunStatus.CANCELLED, finished_at=now)
        )
    run.cancel_requested = True
    audit.record(
        db,
        action="run.cancel",
        actor=user,
        request=request,
        project_id=run.project_id,
        target_type="run",
        target_id=run.id,
        details={"name": run.title},
    )
    await db.commit()
    await db.refresh(run)
    return run_out(run, access.project.key)


@router.get("/api/artifacts/{artifact_id}")
async def download_artifact(artifact_id: uuid.UUID, user: CurrentUser, db: DB) -> FileResponse:
    art = await db.get(Artifact, artifact_id)
    if art is None:
        raise HTTPException(404, NOT_FOUND)
    await run_with_access(db, user, art.run_id)
    root = get_settings().artifacts_dir.resolve()
    path = (root / art.storage_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "File bằng chứng không còn trên máy chủ")
    inline = art.content_type == "image/png"
    return FileResponse(
        Path(path),
        media_type=art.content_type,
        filename=art.filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, max-age=3600"},
    )
