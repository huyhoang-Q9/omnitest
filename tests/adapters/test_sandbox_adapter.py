"""Sandbox chạy script code (pytest/Playwright) trong container Docker.

Phần 1 luôn chạy: kiểm tra định nghĩa, cờ bảo vệ của lệnh docker, đọc kết quả không tin cậy, chặn khi tắt.
Phần 2 chạy với Docker THẬT và image sandbox (bỏ qua nếu thiếu): kiểm chứng cô lập mạng, người dùng không root,
rootfs chỉ đọc, giới hạn bộ nhớ/tiến trình/thời gian, hủy, proxy kiểm soát mạng, che secret và dọn container.
Build image:  docker build -f infra/docker/sandbox.Dockerfile -t omnitest-sandbox:latest .
"""

import asyncio
import io
import os
import subprocess
import tarfile
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from omnitest_adapters.core.base import ExecutionContext
from omnitest_adapters.core.definitions import ScriptTestDefinition, has_side_effect
from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.core.results import Outcome
from omnitest_adapters.core.templating import Variables
from omnitest_adapters.sandbox.adapter import (
    LABEL,
    SandboxConfig,
    SandboxScriptAdapter,
    collect_artifacts,
    parse_junit,
    read_result_tar,
    script_run_args,
)
from pydantic import ValidationError

IMAGE = os.environ.get("OMNITEST_SANDBOX_IMAGE", "omnitest-sandbox:latest")
SECRET = "Mat-khau-sandbox-42"
ADAPTER = SandboxScriptAdapter()


def make_ctx(
    base: str = "http://example.invalid",
    *,
    private: bool = False,
    seconds: float = 120,
    cancel_after: float | None = None,
    allowed: bool = True,
    **cfg: Any,
) -> ExecutionContext:
    started = time.monotonic()

    async def is_cancelled() -> bool:
        return cancel_after is not None and time.monotonic() - started > cancel_after

    return ExecutionContext(
        base_url=base,
        variables=Variables({"USER": "demo", "PASS": SECRET}, {"PASS"}),
        policy=NetworkPolicy.from_environment(base, (), private),
        deadline=time.monotonic() + seconds,
        is_cancelled=is_cancelled,
        settings={
            "sandbox": {"enabled": True, "image": IMAGE, **cfg},
            "script_allowed": allowed,
        },
    )


def script(code: str, network: str = "none", **files: str) -> ScriptTestDefinition:
    return ScriptTestDefinition.model_validate(
        {"kind": "script", "files": {"test_main.py": code, **files}, "network": network}
    )


# ---------- Phần 1: không cần Docker ----------


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"helper.py": "x = 1"},
        {"../test_x.py": "def test(): pass"},
        {"sub/test_x.py": "def test(): pass"},
        {"test_x.sh": "rm -rf /"},
        {"pytest.ini": "[pytest]"},
        {f"test_{i}.py": "" for i in range(21)},
        {"test_big.py": "x" * (257 * 1024)},
    ],
)
def test_definition_rejects_bad_files(files: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ScriptTestDefinition.model_validate({"kind": "script", "files": files})


def test_script_always_counts_as_side_effect() -> None:
    assert has_side_effect(script("def test_ok():\n    pass\n"))


def test_docker_args_are_hardened() -> None:
    args = script_run_args(SandboxConfig(enabled=True, memory_mb=300), "n", None)
    joined = " ".join(args)
    for flag in (
        "--network none",
        "--user 10001:10001",
        "--read-only",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--memory 300m",
        "--memory-swap 300m",
        "--pids-limit",
        "--cpus",
    ):
        assert flag in joined
    assert "docker.sock" not in joined
    assert "-v" not in args  # không mount gì khi không cần proxy
    assert args[-1] == "omnitest-sandbox:latest"


def test_untrusted_result_tar_only_regular_files() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in (("out/exit_code", b"0"), ("etc/passwd", b"x"), ("out/big", b"y" * 50)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("out/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/shadow"
        tar.addfile(link)
    got = read_result_tar(buf.getvalue(), max_file_bytes=10)
    assert got.files == {"exit_code": b"0"}
    assert got.truncated


def test_artifacts_never_rendered_except_real_png() -> None:
    arts = collect_artifacts(
        {
            "artifacts/a.png": b"\x89PNG\r\n\x1a\n...",
            "artifacts/fake.png": b"<script>alert(1)</script>",
            "artifacts/report.html": b"<html>",
            "output.log": b"log",
        }
    )
    by_name = {a.filename: a for a in arts}
    assert by_name["a.png"].content_type == "image/png"
    assert by_name["fake.png"].content_type == "application/octet-stream"
    assert by_name["report.html"].content_type == "application/octet-stream"
    assert "output.log" not in by_name


def test_parse_junit_maps_status_and_masks() -> None:
    xml = f"""<testsuites><testsuite>
      <testcase classname="tests.test_main" name="test_ok" time="0.5"/>
      <testcase classname="tests.test_main" name="test_bad" time="0.1">
        <failure message="assert '{SECRET}' == 'x'">trace {SECRET}</failure></testcase>
      <testcase classname="tests.test_main" name="test_skip"><skipped message="bỏ qua"/></testcase>
    </testsuite></testsuites>""".encode()
    steps = parse_junit(xml, Variables({"PASS": SECRET}, {"PASS"}))
    assert [s.status for s in steps] == [Outcome.PASSED, Outcome.FAILED, Outcome.SKIPPED]
    assert steps[0].name == "test_main::test_ok" and steps[0].duration_ms == 500
    assert SECRET not in (steps[1].error or "") and SECRET not in steps[1].log[0]


def test_parse_junit_refuses_entity_expansion() -> None:
    bomb = b"""<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>
    <testsuites><testcase name="&b;"/></testsuites>"""
    with pytest.raises(Exception, match=r"(?i)entit"):
        parse_junit(bomb, Variables({}, set()))


async def test_blocked_when_server_disabled() -> None:
    c = make_ctx()
    c.settings["sandbox"] = {"enabled": False}
    r = await ADAPTER.execute(c, script("def test_ok():\n    pass\n"))
    assert r.status == Outcome.BLOCKED and r.error_type == "sandbox_disabled"


async def test_blocked_when_project_not_allowed() -> None:
    r = await ADAPTER.execute(make_ctx(allowed=False), script("def test_ok():\n    pass\n"))
    assert r.status == Outcome.BLOCKED and r.error_type == "script_disabled"


async def test_blocked_when_docker_missing() -> None:
    r = await ADAPTER.execute(
        make_ctx(docker_bin="/khong/co/docker"), script("def test_ok():\n    pass\n")
    )
    assert r.status == Outcome.BLOCKED and r.error_type == "sandbox_unavailable"


# ---------- Phần 2: Docker thật ----------


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(  # noqa: S603
                ["docker", "image", "inspect", IMAGE],  # noqa: S607
                capture_output=True,
                timeout=20,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


docker = pytest.mark.skipif(not _docker_ok(), reason=f"Cần Docker và image {IMAGE}")


def _leftovers() -> str:
    ps = subprocess.run(  # noqa: S603
        ["docker", "ps", "-aq", "--filter", f"label={LABEL}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    vols = subprocess.run(  # noqa: S603
        ["docker", "volume", "ls", "-q", "--filter", f"label={LABEL}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return ps + vols


@pytest.fixture
def no_leftovers() -> Iterator[None]:
    yield
    assert _leftovers() == "", "Còn container/volume sandbox chưa dọn"


ISOLATION = r"""
import os, socket, subprocess
from pathlib import Path

def test_runs_as_unprivileged_user():
    assert os.getuid() == 10001 and os.getgid() == 10001
    caps = [l for l in Path("/proc/self/status").read_text().splitlines() if l.startswith("CapEff")]
    assert caps == ["CapEff:\t0000000000000000"]

def test_root_filesystem_is_read_only():
    for p in ("/etc/x", "/opt/omnitest/x", "/usr/x"):
        try:
            Path(p).write_text("x")
        except OSError:
            continue
        raise AssertionError(f"ghi được {p}")

def test_no_network_at_all():
    for host in (("1.1.1.1", 80), ("169.254.169.254", 80), ("172.17.0.1", 80)):
        try:
            socket.create_connection(host, 2)
        except OSError:
            continue
        raise AssertionError(f"kết nối được {host}")

def test_no_docker_socket_and_no_host_files():
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("/run/omnitest/proxy.sock").exists()

def test_variables_and_secret_available_to_script():
    assert os.environ["OMNITEST_VAR_USER"] == "demo"
    print("mat khau la", os.environ["OMNITEST_VAR_PASS"])
    assert os.environ["OMNITEST_BASE_URL"] == "http://example.invalid"

def test_browser_works_without_network(page):
    page.set_content("<h1>Xin chào</h1>")
    assert page.inner_text("h1") == "Xin chào"
    page.screenshot(path=os.environ["OMNITEST_ARTIFACTS_DIR"] + "/trang.png")
    Path(os.environ["OMNITEST_ARTIFACTS_DIR"], "bao-cao.html").write_text("<script>alert(1)</script>")
"""


@docker
async def test_isolated_run_passes_with_evidence(no_leftovers: None) -> None:
    r = await ADAPTER.execute(make_ctx(), script(ISOLATION))
    assert r.status == Outcome.PASSED, (r.error, [(s.name, s.error, s.log) for s in r.steps])
    assert len(r.steps) == 6 and all(s.status == Outcome.PASSED for s in r.steps)
    arts = {a.filename: a for a in r.artifacts}
    log = arts["pytest-output.txt"].data.decode()
    assert SECRET not in log and "mat khau la ***" in log
    assert arts["trang.png"].content_type == "image/png"
    assert arts["bao-cao.html"].content_type == "application/octet-stream"


@docker
async def test_failed_assertion_reports_failed(no_leftovers: None) -> None:
    r = await ADAPTER.execute(
        make_ctx(),
        script(
            "import os\n"
            "def test_ok():\n    pass\n"
            "def test_sai():\n    assert os.environ['OMNITEST_VAR_PASS'] == 'khac'\n"
        ),
    )
    assert r.status == Outcome.FAILED and r.error_type == "assertion"
    assert [s.status for s in r.steps] == [Outcome.PASSED, Outcome.FAILED]
    assert "test_sai" in (r.error or "") and SECRET not in (r.error or "")
    assert SECRET not in " ".join(r.steps[1].log)


@docker
async def test_import_error_is_error_not_pass(no_leftovers: None) -> None:
    r = await ADAPTER.execute(make_ctx(), script("import khong_ton_tai\ndef test_x():\n    pass\n"))
    assert r.status in (Outcome.ERROR, Outcome.FAILED) and r.status != Outcome.PASSED


@docker
async def test_timeout_kills_container(no_leftovers: None) -> None:
    started = time.monotonic()
    r = await ADAPTER.execute(
        make_ctx(seconds=12), script("import time\ndef test_lau():\n    time.sleep(120)\n")
    )
    assert r.status == Outcome.FAILED and r.error_type == "timeout"
    assert time.monotonic() - started < 40


@docker
async def test_cancel_stops_container(no_leftovers: None) -> None:
    r = await ADAPTER.execute(
        make_ctx(cancel_after=4), script("import time\ndef test_lau():\n    time.sleep(120)\n")
    )
    assert r.status == Outcome.CANCELLED


@docker
async def test_memory_limit_enforced(no_leftovers: None) -> None:
    r = await ADAPTER.execute(
        make_ctx(memory_mb=200),
        script("def test_an_ram():\n    x = bytearray(600 * 1024 * 1024)\n    assert x\n"),
    )
    assert r.status in (Outcome.ERROR, Outcome.FAILED), r.error


@docker
async def test_process_limit_enforced(no_leftovers: None) -> None:
    code = (
        "import subprocess\n"
        "def test_nhieu_tien_trinh():\n"
        "    procs = []\n"
        "    try:\n"
        "        for _ in range(200):\n"
        "            procs.append(subprocess.Popen(['sleep', '30']))\n"
        "    except OSError:\n"
        "        return\n"
        "    finally:\n"
        "        for p in procs:\n"
        "            p.kill()\n"
        "    raise AssertionError('tạo được 200 tiến trình')\n"
    )
    r = await ADAPTER.execute(make_ctx(pids_limit=64), script(code))
    assert r.status == Outcome.PASSED, (r.error, [s.log for s in r.steps])


@docker
async def test_output_limit(no_leftovers: None) -> None:
    code = (
        "import os\n"
        "def test_file_lon():\n"
        "    with open(os.environ['OMNITEST_ARTIFACTS_DIR'] + '/lon.bin', 'wb') as f:\n"
        "        f.write(os.urandom(30 * 1024 * 1024))\n"
    )
    r = await ADAPTER.execute(make_ctx(max_output_bytes=5 * 1024 * 1024), script(code))
    assert r.status == Outcome.ERROR and r.error_type == "sandbox_output_limit"


# ---------- Mạng qua proxy kiểm soát ----------


def _bridge_gateway() -> str:
    return subprocess.run(
        ["docker", "network", "inspect", "bridge", "-f", "{{(index .IPAM.Config 0).Gateway}}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


class _Hello(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<html><title>Trang test</title><h1>xin chao sandbox</h1></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def host_site() -> Iterator[str]:
    srv = ThreadingHTTPServer(("0.0.0.0", 0), _Hello)  # noqa: S104 - container cần thấy máy chủ test
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://{_bridge_gateway()}:{srv.server_address[1]}"
    finally:
        srv.shutdown()


NETWORK = r"""
import os, socket
import httpx

BASE = os.environ["OMNITEST_BASE_URL"]

def test_allowed_target_via_proxy():
    r = httpx.get(BASE, timeout=10)
    assert r.status_code == 200 and "xin chao sandbox" in r.text

def test_browser_via_proxy(page):
    page.goto(BASE)
    assert page.title() == "Trang test"

def test_metadata_blocked():
    r = httpx.get("http://169.254.169.254/latest/meta-data/", timeout=10)
    assert r.status_code == 403

def test_other_host_blocked():
    r = httpx.get("http://example.com/", timeout=10)
    assert r.status_code == 403

def test_direct_connection_still_impossible():
    host, port = BASE.split("//")[1].split(":")
    try:
        socket.create_connection((host, int(port)), 2)
    except OSError:
        return
    raise AssertionError("đi thẳng được, không qua proxy")
"""


@docker
async def test_network_environment_goes_through_policy_proxy(
    host_site: str, no_leftovers: None
) -> None:
    r = await ADAPTER.execute(make_ctx(host_site, private=True), script(NETWORK, "environment"))
    assert r.status == Outcome.PASSED, (r.error, [(s.name, s.error, s.log) for s in r.steps])
    blocked = next(a for a in r.artifacts if a.filename == "proxy-bi-chan.txt").data.decode()
    assert "169.254.169.254" in blocked and "example.com" in blocked


@docker
async def test_private_network_blocked_unless_enabled(host_site: str, no_leftovers: None) -> None:
    code = (
        "import os, httpx\n"
        "def test_goi():\n"
        "    assert httpx.get(os.environ['OMNITEST_BASE_URL'], timeout=10).status_code == 200\n"
    )
    r = await ADAPTER.execute(make_ctx(host_site, private=False), script(code, "environment"))
    assert r.status == Outcome.FAILED
    assert "chặn" in (r.error or "")


@docker
async def test_parallel_runs_are_independent(no_leftovers: None) -> None:
    results = await asyncio.gather(
        *(ADAPTER.execute(make_ctx(), script("def test_ok():\n    pass\n")) for _ in range(3))
    )
    assert all(r.status == Outcome.PASSED for r in results)
