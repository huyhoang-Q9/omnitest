"""Kiểm tra khói (smoke test) cho stack Docker Compose đang chạy, chỉ dùng thư viện chuẩn.

Đi qua nginx (cổng 8080) như người dùng thật: tạo quản trị hệ thống, tạo dự án demo, chạy suite Smoke qua worker
(API + Web bằng Chromium trong container) và chờ kết quả. Với --sandbox: bật script code cho dự án, chạy một test
pytest trong sandbox Docker. Thoát mã khác 0 nếu có bước không đạt.

    python infra/scripts/compose_smoke.py -f infra/docker/compose.yaml [-f infra/docker/compose.sandbox.yaml] \
        --env-file .env [--sandbox]
"""

import argparse
import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8080"
EMAIL = "smoke@omnitest.local"


class Client:
    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def call(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(  # noqa: S310 - URL cố định tới stack local
            BASE + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-OmniTest-CSRF": "1"},
        )
        try:
            with self.opener.open(req, timeout=30) as res:
                raw = res.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read()[:500]!r}") from exc
        return json.loads(raw) if raw else None


def compose(files: list[str], env_file: str, *args: str, env: dict[str, str] | None = None) -> str:
    cmd = [
        "docker",
        "compose",
        *[x for f in files for x in ("-f", f)],
        "--env-file",
        env_file,
        *args,
    ]
    res = subprocess.run(  # noqa: S603 - lệnh docker compose cố định
        cmd, capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False
    )
    if res.returncode != 0:
        raise SystemExit(f"Lỗi: {' '.join(args)}\n{res.stdout}\n{res.stderr}")
    return res.stdout


def wait_health(seconds: int = 240) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=5) as res:  # noqa: S310
                if json.loads(res.read()).get("status") == "ok":
                    return
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(2)
    raise SystemExit("API không sẵn sàng qua nginx")


def run_and_wait(c: Client, pid: str, body: dict[str, Any], seconds: int = 300) -> dict[str, Any]:
    run = c.call("POST", f"/api/projects/{pid}/runs", {**body, "confirm": True})
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        detail: dict[str, Any] = c.call("GET", f"/api/runs/{run['id']}")
        if detail["status"] not in ("queued", "running"):
            return detail
        time.sleep(2)
    raise SystemExit(f"Lần chạy {run['id']} chưa xong sau {seconds} giây")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", dest="files", action="append", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--sandbox", action="store_true")
    a = ap.parse_args()

    wait_health()
    print("OK  API và web sẵn sàng qua nginx")
    password = "Smoke-" + secrets.token_urlsafe(12) + "9a"
    compose(
        a.files,
        a.env_file,
        "exec",
        "-T",
        "-e",
        "OMNITEST_ADMIN_PASSWORD",
        "api",
        "omnitest-api",
        "create-admin",
        "--email",
        EMAIL,
        env={"OMNITEST_ADMIN_PASSWORD": password},
    )
    compose(
        a.files,
        a.env_file,
        "exec",
        "-T",
        "api",
        "omnitest-api",
        "seed-demo",
        "--owner-email",
        EMAIL,
        "--base-url",
        "http://demo:8100",
    )
    c = Client()
    c.call("POST", "/api/auth/login", {"email": EMAIL, "password": password})
    projects = c.call("GET", "/api/projects?page_size=100")["items"]
    pid = next(p["id"] for p in projects if p["key"] == "DEMO")
    eid = c.call("GET", f"/api/projects/{pid}/environments")[0]["id"]
    suite = next(s for s in c.call("GET", f"/api/projects/{pid}/suites") if s["name"] == "Smoke")
    print("OK  tạo quản trị, dự án demo")

    detail = run_and_wait(c, pid, {"environment_id": eid, "suite_id": suite["id"]})
    summary = ", ".join(f"{i['code']}={i['status']}" for i in detail["items"])
    if detail["status"] != "passed":
        print(f"FAIL suite Smoke: {detail['status']} ({summary})")
        return 1
    print(f"OK  suite Smoke qua worker: {summary}")

    if a.sandbox:
        c.call("PATCH", f"/api/projects/{pid}", {"script_enabled": True})
        code = (
            "import os, socket\n"
            "def test_khong_co_mang():\n"
            "    try:\n"
            "        socket.create_connection(('1.1.1.1', 80), 2)\n"
            "    except OSError:\n"
            "        return\n"
            "    raise AssertionError('container sandbox có mạng')\n"
            "def test_khong_phai_root():\n"
            "    assert os.getuid() != 0\n"
        )
        case = c.call(
            "POST",
            f"/api/projects/{pid}/test-cases",
            {
                "title": "Smoke sandbox",
                "test_type": "script",
                "definition": {"kind": "script", "files": {"test_smoke.py": code}},
            },
        )
        detail = run_and_wait(c, pid, {"environment_id": eid, "test_case_ids": [case["id"]]})
        item = detail["items"][0]
        if detail["status"] != "passed":
            print(f"FAIL sandbox: {detail['status']} {item.get('error_type')} {item.get('error')}")
            return 1
        print("OK  script pytest chạy trong sandbox từ worker container")
    return 0


if __name__ == "__main__":
    sys.exit(main())
