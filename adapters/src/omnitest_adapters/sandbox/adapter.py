"""Chạy script pytest/Playwright do người dùng viết trong container Docker cô lập.

Không bao giờ chạy code người dùng trong tiến trình worker hay trên máy chủ chính. Mỗi lần chạy:
- Một container mới từ image sandbox, người dùng không root (uid 10001), rootfs chỉ đọc, /tmp là tmpfs có hạn mức,
  bỏ mọi capability, no-new-privileges, giới hạn CPU, RAM (không swap), số tiến trình, thời gian.
- Không mount thư mục hay Docker socket của máy chủ. Code đi vào qua stdin (tar), kết quả đi ra qua stdout (tar).
- Mạng mặc định: không có (--network none). Chế độ "environment": container vẫn không có card mạng, chỉ đi ra
  qua container proxy riêng (nối bằng Unix socket trên volume tạm), proxy kiểm tra từng đích theo chính sách
  của môi trường (allowlist, chặn mạng nội bộ nếu chưa bật, luôn chặn metadata cloud).
- Luôn xóa container, proxy và volume khi xong, kể cả khi hủy, quá giờ hay lỗi.

Chỉ chạy khi máy chủ bật sandbox (OMNITEST_SANDBOX_ENABLED) VÀ Admin dự án bật "cho phép script code".
"""

import asyncio
import contextlib
import io
import json
import re
import tarfile
import time
import uuid
from dataclasses import dataclass
from typing import Any

from defusedxml import ElementTree

from omnitest_adapters.core.base import (
    Capabilities,
    EnvironmentCheck,
    ExecutionContext,
    SupportStatus,
)
from omnitest_adapters.core.definitions import ScriptTestDefinition
from omnitest_adapters.core.results import AdapterResult, ArtifactFile, Outcome, StepOutcome
from omnitest_adapters.core.templating import Variables

SANDBOX_UID = "10001:10001"
LABEL = "omnitest.sandbox=1"
MAX_STEPS = 500
MAX_ARTIFACTS = 20
MAX_LOG_CHARS = 2_000_000
CLEANUP_MARGIN_SECONDS = 3
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class SandboxConfig:
    enabled: bool = False
    image: str = "omnitest-sandbox:latest"
    docker_bin: str = "docker"
    cpus: float = 1.0
    memory_mb: int = 1024
    pids_limit: int = 256
    tmpfs_mb: int = 512
    max_output_bytes: int = 50 * 1024 * 1024
    max_artifact_bytes: int = 10 * 1024 * 1024
    proxy_network: str = "bridge"

    @classmethod
    def from_settings(cls, value: Any) -> "SandboxConfig":
        if isinstance(value, SandboxConfig):
            return value
        if isinstance(value, dict):
            return cls(**{k: v for k, v in value.items() if k in cls.__dataclass_fields__})
        return cls()


class _DockerError(Exception):
    pass


async def _docker(
    cfg: SandboxConfig,
    *args: str,
    timeout: float = 60,  # noqa: ASYNC109 - mỗi lệnh docker có hạn riêng
) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            cfg.docker_bin,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise _DockerError(f"Không gọi được Docker CLI '{cfg.docker_bin}': {exc.strerror}") from exc
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as exc:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        raise _DockerError(f"Lệnh docker {args[0]} quá thời gian") from exc
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def hardening_args(*, keep_logs: bool = False) -> list[str]:
    """Cờ bảo vệ dùng chung cho container chạy test và container proxy."""
    args = [
        "--label",
        LABEL,
        "--user",
        SANDBOX_UID,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--ulimit",
        "nofile=1024:1024",
    ]
    return args if keep_logs else [*args, "--log-driver", "none"]


def script_run_args(cfg: SandboxConfig, name: str, volume: str | None) -> list[str]:
    args = [
        "run",
        "-i",
        "--name",
        name,
        *hardening_args(),
        "--network",
        "none",
        "--hostname",
        "sandbox",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={cfg.tmpfs_mb}m",  # noqa: S108 - tmpfs bên trong container
        "--shm-size",
        "256m",
        "--pids-limit",
        str(cfg.pids_limit),
        "--memory",
        f"{cfg.memory_mb}m",
        "--memory-swap",
        f"{cfg.memory_mb}m",
        "--cpus",
        str(cfg.cpus),
    ]
    if volume:
        args += ["-v", f"{volume}:/run/omnitest"]
    return [*args, cfg.image]


def proxy_run_args(cfg: SandboxConfig, name: str, volume: str, policy: dict[str, Any]) -> list[str]:
    return [
        "run",
        "-d",
        "--name",
        name,
        *hardening_args(keep_logs=True),  # đọc log của proxy để biết kết nối nào bị chặn
        "--network",
        cfg.proxy_network,
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--cpus",
        "0.5",
        "-v",
        f"{volume}:/run/omnitest",
        "-e",
        f"OMNITEST_PROXY_POLICY={json.dumps(policy)}",
        "--entrypoint",
        "python",
        cfg.image,
        "/opt/omnitest/proxy_main.py",
    ]


def build_payload(definition: ScriptTestDefinition, base_url: str, variables: Variables) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:

        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))

        cfg = {
            "base_url": base_url,
            "variables": variables.as_dict(),
            "network": definition.network,
        }
        add(".omnitest.json", json.dumps(cfg).encode())
        for fname, content in definition.files.items():
            add(f"tests/{fname}", content.encode())
    return buf.getvalue()


@dataclass
class _Collected:
    files: dict[str, bytes]
    truncated: bool


def read_result_tar(data: bytes, max_file_bytes: int) -> _Collected:
    """Đọc tar kết quả do container trả về (dữ liệu không tin cậy): chỉ lấy file thường trong out/."""
    files: dict[str, bytes] = {}
    truncated = False
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        for member in tar:
            if not member.isfile() or not member.name.startswith("out/") or ".." in member.name:
                continue
            if member.size > max_file_bytes:
                truncated = True
                continue
            f = tar.extractfile(member)
            if f is not None:
                files[member.name.removeprefix("out/")] = f.read()
    return _Collected(files, truncated)


def parse_junit(xml: bytes, variables: Variables) -> list[StepOutcome]:
    root = ElementTree.fromstring(xml)
    steps: list[StepOutcome] = []
    for case in root.iter("testcase"):
        if len(steps) >= MAX_STEPS:
            break
        classname = str(case.get("classname") or "").removeprefix("tests.")
        name = f"{classname}::{case.get('name')}" if classname else str(case.get("name"))
        try:
            duration_ms = int(float(case.get("time") or 0) * 1000)
        except ValueError:
            duration_ms = 0
        status, error, log = Outcome.PASSED, None, []
        for tag, outcome in (
            ("failure", Outcome.FAILED),
            ("error", Outcome.ERROR),
            ("skipped", Outcome.SKIPPED),
        ):
            node = case.find(tag)
            if node is not None:
                status = outcome
                error = str(node.get("message") or tag)[:1000]
                if node.text:
                    log = [node.text[-4000:]]
                break
        steps.append(
            StepOutcome(
                len(steps),
                variables.mask(name[:200]),
                status,
                duration_ms,
                [variables.mask(x) for x in log],
                variables.mask(error) if error else None,
                {"runner": "pytest"},
            )
        )
    return steps


def collect_artifacts(files: dict[str, bytes]) -> list[ArtifactFile]:
    """File người dùng ghi vào OMNITEST_ARTIFACTS_DIR. Chỉ PNG đúng chữ ký mới được hiển thị như ảnh;
    mọi file khác lưu dạng tải về (application/octet-stream) để không bao giờ được trình duyệt hiển thị."""
    out: list[ArtifactFile] = []
    for path, data in sorted(files.items()):
        if not path.startswith("artifacts/") or len(out) >= MAX_ARTIFACTS:
            continue
        fname = SAFE_NAME.sub("_", path.removeprefix("artifacts/"))[:100] or "file"
        if data.startswith(PNG_MAGIC):
            out.append(ArtifactFile("screenshot", fname, "image/png", data))
        else:
            out.append(ArtifactFile("file", fname, "application/octet-stream", data))
    return out


class SandboxScriptAdapter:
    key = "script_sandbox"
    display_name = "Script code (pytest/Playwright) trong sandbox Docker"
    status = SupportStatus.EXPERIMENTAL
    test_kinds = ("script",)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            test_kinds=list(self.test_kinds),
            features=["pytest", "playwright", "docker", "no-network-default"],
        )

    def check_environment(self) -> EnvironmentCheck:
        return EnvironmentCheck(
            True,
            "Cần Docker và image sandbox trên máy worker, máy chủ bật OMNITEST_SANDBOX_ENABLED và dự án "
            "bật cho phép script code; thiếu thì lần chạy báo Bị chặn",
        )

    async def execute(
        self, ctx: ExecutionContext, definition: ScriptTestDefinition
    ) -> AdapterResult:
        cfg = SandboxConfig.from_settings(ctx.settings.get("sandbox"))
        if not cfg.enabled:
            return AdapterResult(
                Outcome.BLOCKED,
                [],
                "Máy chủ chưa bật sandbox chạy script code (OMNITEST_SANDBOX_ENABLED)",
                "sandbox_disabled",
            )
        if not ctx.settings.get("script_allowed"):
            return AdapterResult(
                Outcome.BLOCKED,
                [],
                "Dự án chưa bật cho phép chạy script code (Admin dự án bật trong trang dự án)",
                "script_disabled",
            )
        try:
            rc, _, err = await _docker(cfg, "image", "inspect", "--format", "{{.Id}}", cfg.image)
        except _DockerError as exc:
            return AdapterResult(Outcome.BLOCKED, [], str(exc), "sandbox_unavailable")
        if rc != 0:
            return AdapterResult(
                Outcome.BLOCKED,
                [],
                f"Không dùng được Docker hoặc chưa có image sandbox '{cfg.image}': {err.strip()[:300]}",
                "sandbox_unavailable",
            )

        name = f"omnitest-sbx-{uuid.uuid4().hex[:16]}"
        proxy_name = f"{name}-proxy"
        volume = name if definition.network == "environment" else None
        try:
            return await self._run(ctx, cfg, definition, name, proxy_name, volume)
        except _DockerError as exc:
            return AdapterResult(Outcome.BLOCKED, [], str(exc), "sandbox_unavailable")
        finally:
            await self._cleanup(cfg, name, proxy_name, volume)

    async def _cleanup(
        self, cfg: SandboxConfig, name: str, proxy_name: str, volume: str | None
    ) -> None:
        with contextlib.suppress(_DockerError):
            await _docker(cfg, "rm", "-f", name, proxy_name, timeout=30)
            if volume:
                await _docker(cfg, "volume", "rm", "-f", volume, timeout=30)

    async def _start_proxy(
        self, ctx: ExecutionContext, cfg: SandboxConfig, proxy_name: str, volume: str
    ) -> str | None:
        rc, _, err = await _docker(cfg, "volume", "create", "--label", LABEL, volume)
        if rc != 0:
            return f"Không tạo được volume cho proxy: {err.strip()[:300]}"
        policy = {
            "allowed_hosts": list(ctx.policy.allowed_hosts),
            "allow_private_network": ctx.policy.allow_private_network,
        }
        rc, _, err = await _docker(cfg, *proxy_run_args(cfg, proxy_name, volume, policy))
        if rc != 0:
            return f"Không khởi động được proxy của sandbox: {err.strip()[:300]}"
        for _ in range(75):
            _, out, _ = await _docker(cfg, "logs", proxy_name)
            if "READY" in out:
                return None
            await asyncio.sleep(0.2)
        return "Proxy của sandbox không sẵn sàng sau 15 giây"

    async def _run(
        self,
        ctx: ExecutionContext,
        cfg: SandboxConfig,
        definition: ScriptTestDefinition,
        name: str,
        proxy_name: str,
        volume: str | None,
    ) -> AdapterResult:
        v = ctx.variables
        if volume:
            problem = await self._start_proxy(ctx, cfg, proxy_name, volume)
            if problem:
                return AdapterResult(Outcome.BLOCKED, [], problem, "sandbox_unavailable")

        payload = build_payload(definition, ctx.base_url, v)
        try:
            proc = await asyncio.create_subprocess_exec(
                cfg.docker_bin,
                *script_run_args(cfg, name, volume),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise _DockerError(f"Không gọi được Docker CLI: {exc.strerror}") from exc
        assert proc.stdin and proc.stdout and proc.stderr
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            proc.stdin.write(payload)
            await proc.stdin.drain()
            proc.stdin.close()

        chunks: list[bytes] = []
        size = 0
        over_limit = False

        async def read_stdout() -> None:
            nonlocal size, over_limit
            assert proc.stdout
            while data := await proc.stdout.read(65536):
                size += len(data)
                if size > cfg.max_output_bytes:
                    over_limit = True
                    return
                chunks.append(data)

        reader = asyncio.create_task(read_stdout())
        err_task = asyncio.create_task(proc.stderr.read(64 * 1024))
        deadline = ctx.deadline - CLEANUP_MARGIN_SECONDS
        stopped: tuple[Outcome, str, str] | None = None
        finished = False
        started = time.monotonic()
        try:
            while not reader.done():
                await asyncio.wait({reader}, timeout=1.0)
                if reader.done():
                    break
                if await ctx.is_cancelled():
                    stopped = (Outcome.CANCELLED, "Người dùng đã hủy lần chạy", "cancelled")
                elif time.monotonic() >= deadline:
                    stopped = (
                        Outcome.FAILED,
                        f"Script chạy quá thời gian cho phép ({int(time.monotonic() - started)} giây)",
                        "timeout",
                    )
                if stopped:
                    break
            if over_limit and not stopped:
                stopped = (
                    Outcome.ERROR,
                    f"Kết quả của script vượt {cfg.max_output_bytes // (1024 * 1024)} MB",
                    "sandbox_output_limit",
                )
            finished = not stopped
        finally:
            if not finished:
                # Hủy, quá giờ, vượt hạn mức hoặc worker bị dừng giữa chừng. Ngắt CLI trước để luồng attach
                # không còn bị nghẽn (nếu không, lệnh docker kill có thể chờ), rồi dừng container.
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(_DockerError):
                    await _docker(cfg, "kill", name, timeout=30)
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
            await proc.wait()
        stderr = (await err_task).decode(errors="replace")

        blocked: list[str] = []
        if volume:
            _, logs, _ = await _docker(cfg, "logs", proxy_name)
            blocked = [
                ln.removeprefix("BLOCKED ") for ln in logs.splitlines() if ln.startswith("BLOCKED ")
            ]
        _, state, _ = await _docker(cfg, "inspect", "--format", "{{.State.OOMKilled}}", name)
        oom = state.strip() == "true"

        if stopped:
            return AdapterResult(stopped[0], [], stopped[1], stopped[2], self._proxy_log(blocked))
        if oom:
            return AdapterResult(
                Outcome.ERROR,
                [],
                f"Script dùng vượt giới hạn bộ nhớ {cfg.memory_mb} MB và bị dừng",
                "sandbox_oom",
                self._proxy_log(blocked),
            )
        try:
            collected = read_result_tar(b"".join(chunks), cfg.max_artifact_bytes)
        except tarfile.TarError:
            return AdapterResult(
                Outcome.ERROR,
                [],
                v.mask(
                    f"Container sandbox không trả kết quả hợp lệ (mã {proc.returncode}): {stderr.strip()[:500]}"
                ),
                "sandbox_error",
                self._proxy_log(blocked),
            )
        return self._result(collected, v, blocked)

    @staticmethod
    def _proxy_log(blocked: list[str]) -> list[ArtifactFile]:
        if not blocked:
            return []
        text = "Kết nối bị proxy của sandbox chặn:\n" + "\n".join(blocked[:500])
        return [
            ArtifactFile("log", "proxy-bi-chan.txt", "text/plain; charset=utf-8", text.encode())
        ]

    def _result(self, collected: _Collected, v: Variables, blocked: list[str]) -> AdapterResult:
        files = collected.files
        artifacts = self._proxy_log(blocked)
        if "output.log" in files:
            text = v.mask(files["output.log"].decode(errors="replace"))
            if len(text) > MAX_LOG_CHARS:
                text = "...(đã cắt phần đầu)...\n" + text[-MAX_LOG_CHARS:]
            artifacts.append(
                ArtifactFile("log", "pytest-output.txt", "text/plain; charset=utf-8", text.encode())
            )
        artifacts += collect_artifacts(files)
        if files.get("status", b"").strip() == b"proxy_unavailable":
            return AdapterResult(
                Outcome.BLOCKED,
                [],
                "Script không nối được proxy của sandbox",
                "sandbox_unavailable",
                artifacts,
            )
        steps: list[StepOutcome] = []
        if "junit.xml" in files:
            try:
                steps = parse_junit(files["junit.xml"], v)
            except ElementTree.ParseError:
                steps = []
        try:
            code = int(files.get("exit_code", b"").strip() or b"-1")
        except ValueError:
            code = -1
        hint = f" Kết nối bị chặn: {blocked[0]}" if blocked else ""
        if code == 0:
            return AdapterResult(Outcome.PASSED, steps, None, None, artifacts)
        if code == 1:
            bad = [s for s in steps if s.status in (Outcome.FAILED, Outcome.ERROR)]
            first = f"{bad[0].name}: {bad[0].error}" if bad else "pytest báo có test không đạt"
            status = (
                Outcome.FAILED if any(s.status == Outcome.FAILED for s in bad) else Outcome.ERROR
            )
            return AdapterResult(
                status,
                steps,
                v.mask(f"{len(bad)} test không đạt. {first}{hint}")[:2000],
                "assertion",
                artifacts,
            )
        if code == 5:
            return AdapterResult(
                Outcome.ERROR,
                steps,
                "pytest không tìm thấy test nào để chạy",
                "no_tests",
                artifacts,
            )
        reason = {2: "bị ngắt", 3: "lỗi nội bộ của pytest", 4: "lỗi cách gọi hoặc lỗi import"}.get(
            code, "thoát bất thường"
        )
        if collected.truncated:
            reason += "; có file kết quả vượt giới hạn kích thước bị bỏ"
        return AdapterResult(
            Outcome.ERROR,
            steps,
            f"pytest {reason} (mã {code}). Xem pytest-output.txt.{hint}",
            "script_error",
            artifacts,
        )
