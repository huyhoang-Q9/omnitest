"""Chạy BÊN TRONG container sandbox (người dùng không root, không mạng, rootfs chỉ đọc).

Giao tiếp với worker chỉ qua stdin/stdout, không mount thư mục nào của máy chủ:
- stdin: tar gồm .omnitest.json (cấu hình lần chạy) và tests/<file của người dùng>.
- stdout: tar thư mục kết quả /tmp/out (junit.xml, output.log, exit_code, artifacts/).

Khi lần chạy được phép ra mạng, container vẫn không có card mạng; bootstrap mở cổng 127.0.0.1:3128 chuyển tiếp
sang Unix socket của container proxy (proxy kiểm tra từng đích theo chính sách của môi trường).
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

WORK = Path("/tmp/work")
OUT = Path("/tmp/out")
RUNTIME = Path("/opt/omnitest")
PROXY_SOCK = "/run/omnitest/proxy.sock"
PROXY_PORT = 3128


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client: socket.socket) -> None:
    upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        upstream.connect(PROXY_SOCK)
    except OSError:
        client.close()
        upstream.close()
        return
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
    _pipe(upstream, client)
    client.close()
    upstream.close()


def _serve_proxy(server: socket.socket) -> None:
    while True:
        client, _ = server.accept()
        threading.Thread(target=_handle, args=(client,), daemon=True).start()


def _start_proxy_bridge() -> bool:
    for _ in range(150):
        if os.path.exists(PROXY_SOCK):
            break
        time.sleep(0.1)
    else:
        return False
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", PROXY_PORT))
    server.listen(128)
    threading.Thread(target=_serve_proxy, args=(server,), daemon=True).start()
    return True


def _emit_results() -> None:
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
        tar.add(OUT, arcname="out")
    sys.stdout.buffer.flush()


def main() -> int:
    WORK.mkdir(parents=True)
    (OUT / "artifacts").mkdir(parents=True)
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as tar:
        tar.extractall(WORK, filter="data")
    cfg = json.loads((WORK / ".omnitest.json").read_text(encoding="utf-8"))
    (WORK / ".omnitest.json").unlink()
    shutil.copy(RUNTIME / "conftest.py", WORK / "conftest.py")
    shutil.copy(RUNTIME / "pytest.ini", WORK / "pytest.ini")

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright"),
        "OMNITEST_BASE_URL": cfg["base_url"],
        "OMNITEST_ARTIFACTS_DIR": str(OUT / "artifacts"),
    }
    for key, value in cfg["variables"].items():
        env[f"OMNITEST_VAR_{key}"] = value
    if cfg["network"] == "environment":
        if not _start_proxy_bridge():
            (OUT / "status").write_text("proxy_unavailable")
            _emit_results()
            return 0
        proxy = f"http://127.0.0.1:{PROXY_PORT}"
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "OMNITEST_PROXY"):
            env[name] = proxy

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-rA",
        "-o",
        "junit_family=xunit2",
        "--junitxml",
        str(OUT / "junit.xml"),
        "--base-url",
        cfg["base_url"],
    ]
    with (OUT / "output.log").open("wb") as log:
        proc = subprocess.run(  # noqa: S603 - lệnh cố định, chạy trong container cô lập
            cmd, cwd=WORK, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
        )
    (OUT / "exit_code").write_text(str(proc.returncode))
    _emit_results()
    return 0


if __name__ == "__main__":
    sys.exit(main())
