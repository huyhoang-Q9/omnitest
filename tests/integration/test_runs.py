"""Luồng chạy test đầu cuối: API tạo run, worker executor chạy thật với demo-target, kết quả đọc lại qua API.

Không mock adapter hay HTTP: executor gọi demo-target thật trên cổng ngẫu nhiên.
"""

import asyncio
import io
import json
import os
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from omnitest_worker.executor import RunExecutor, final_run_status
from sqlalchemy import update

from omnitest_api.db import get_engine, get_sessionmaker
from omnitest_api.models import RunStatus, TestRun, TestRunItem
from tests.conftest import LoginAs, MakeUser
from tests.integration.phase3_helpers import API_HEALTH, case_body, setup_project

SECRET = "Demo@123"

API_LOGIN_OK: dict[str, Any] = {
    "kind": "api",
    "steps": [
        {
            "name": "Đăng nhập",
            "method": "POST",
            "url": "/api/login",
            "body_type": "json",
            "body": {"username": "demo", "password": "{{DEMO_PASSWORD}}"},
            "assertions": [{"type": "status", "equals": 200}],
            "extract": [{"var": "TOKEN", "source": "json_path", "expression": "$.token"}],
        },
        {
            "name": "Danh sách",
            "url": "/api/items",
            "auth": {"type": "bearer", "token": "{{TOKEN}}"},
            "assertions": [
                {"type": "status", "equals": 200},
                {"type": "json_path", "path": "$.total", "value": 2},
            ],
        },
    ],
}
API_UNAUTHORIZED: dict[str, Any] = {
    "kind": "api",
    "steps": [
        {
            "name": "Không token",
            "url": "/api/items",
            "assertions": [{"type": "status", "equals": 200}],
        }
    ],
}


def slow(seconds: float) -> dict[str, Any]:
    return {
        "kind": "api",
        "steps": [
            {
                "name": "Chậm",
                "url": f"/api/slow?seconds={seconds}",
                "timeout_ms": 30000,
                "assertions": [{"type": "status", "equals": 200}],
            }
        ],
    }


@pytest.fixture(autouse=True)
def _reset_demo(demo_url: str) -> None:
    httpx.post(f"{demo_url}/api/reset", trust_env=False)


async def _root(make_user: MakeUser, login_as: LoginAs) -> httpx.AsyncClient:
    await make_user("root@x.vn", admin=True)
    return await login_as("root@x.vn")


async def _case(
    c: httpx.AsyncClient, pid: str, title: str, definition: dict[str, Any], **kw: Any
) -> str:
    r = await c.post(f"/api/projects/{pid}/test-cases", json=case_body(title, definition, **kw))
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _run(
    c: httpx.AsyncClient, pid: str, eid: str, ids: list[str], confirm: bool = False
) -> httpx.Response:
    return await c.post(
        f"/api/projects/{pid}/runs",
        json={"environment_id": eid, "test_case_ids": ids, "confirm": confirm},
    )


async def _execute(run_id: str) -> RunStatus | None:
    return await RunExecutor(get_engine()).execute_run(uuid.UUID(run_id))


async def test_pass_fail_counters_and_secret_masking(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    ok = await _case(root, pid, "Đăng nhập và xem hàng", API_LOGIN_OK)
    bad = await _case(root, pid, "Gọi không token", API_UNAUTHORIZED)
    health = await _case(root, pid, "Health", API_HEALTH)

    r = await _run(root, pid, eid, [ok, bad, health], confirm=True)
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "queued" and run["total"] == 3

    assert await _execute(run["id"]) == RunStatus.FAILED
    detail = (await root.get(f"/api/runs/{run['id']}")).json()
    assert (detail["passed"], detail["failed"]) == (2, 1)
    assert [i["status"] for i in detail["items"]] == ["passed", "failed", "passed"]
    assert detail["items"][1]["error_type"] == "assertion"
    assert detail["started_at"] and detail["finished_at"] and detail["duration_ms"] is not None

    item = (await root.get(f"/api/run-items/{detail['items'][0]['id']}")).json()
    assert [s["status"] for s in item["steps"]] == ["passed", "passed"]
    # Secret và token trích xuất không xuất hiện ở bất kỳ đâu trong kết quả trả về.
    dumped = json.dumps(item, ensure_ascii=False)
    assert SECRET not in dumped
    assert "***" in dumped


async def test_confirmation_required_for_side_effect(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    ok = await _case(root, pid, "Đăng nhập", API_LOGIN_OK)
    r = await _run(root, pid, eid, [ok])
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["code"] == "confirmation_required" and "DEMO-TC-0001" in body["reasons"][0]
    assert (await root.get(f"/api/projects/{pid}/runs")).json()["total"] == 0
    assert (await _run(root, pid, eid, [ok], confirm=True)).status_code == 201


async def test_production_environment_requires_confirmation(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, _ = await setup_project(root, demo_url)
    prod = await root.post(
        f"/api/projects/{pid}/environments",
        json={
            "name": "Staging",
            "kind": "staging",
            "base_url": demo_url,
            "allow_private_network": True,
        },
    )
    health = await _case(root, pid, "Health", API_HEALTH)
    r = await _run(root, pid, prod.json()["id"], [health])
    assert r.status_code == 409 and "STAGING" in r.json()["detail"]["reasons"][0]


async def test_retry_only_without_side_effect(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    get_fail = await _case(root, pid, "GET lỗi", API_UNAUTHORIZED, retry_count=2)
    post_fail = {
        "kind": "api",
        "steps": [
            {
                "name": "Tạo không token",
                "method": "POST",
                "url": "/api/items",
                "body_type": "json",
                "body": {"name": "x", "quantity": 1},
                "assertions": [{"type": "status", "equals": 201}],
            }
        ],
    }
    side = await _case(root, pid, "POST lỗi", post_fail, retry_count=2)
    run = (await _run(root, pid, eid, [get_fail, side], confirm=True)).json()
    await _execute(run["id"])
    items = (await root.get(f"/api/runs/{run['id']}")).json()["items"]
    assert items[0]["attempts"] == 3 and items[0]["status"] == "failed"
    # Test có side effect không bao giờ tự thử lại.
    assert items[1]["side_effect"] is True and items[1]["attempts"] == 1
    steps = (await root.get(f"/api/run-items/{items[0]['id']}")).json()["steps"]
    assert [s["attempt"] for s in steps] == [1, 2, 3]


async def test_item_timeout(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    cid = await _case(root, pid, "Chậm", slow(4), retry_count=1)
    run = (await _run(root, pid, eid, [cid])).json()
    # Giới hạn API tối thiểu 5 giây; hạ trực tiếp trong DB để test nhanh.
    async with get_sessionmaker()() as db:
        await db.execute(
            update(TestRunItem)
            .where(TestRunItem.run_id == uuid.UUID(run["id"]))
            .values(timeout_seconds=1)
        )
        await db.commit()
    assert await _execute(run["id"]) == RunStatus.FAILED
    item = (await root.get(f"/api/runs/{run['id']}")).json()["items"][0]
    assert item["error_type"] == "timeout" and item["attempts"] == 2
    assert item["duration_ms"] < 3500


async def test_cancel_queued_run_is_skipped_by_worker(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    cid = await _case(root, pid, "Health", API_HEALTH)
    run = (await _run(root, pid, eid, [cid])).json()
    r = await root.post(f"/api/runs/{run['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert await _execute(run["id"]) == RunStatus.CANCELLED
    assert (await root.get(f"/api/runs/{run['id']}")).json()["items"][0]["attempts"] == 0
    assert (await root.post(f"/api/runs/{run['id']}/cancel")).status_code == 409


async def test_cancel_running_run(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    a = await _case(root, pid, "Chậm 1", slow(1.5))
    b = await _case(root, pid, "Chậm 2", slow(1.5))
    run = (await _run(root, pid, eid, [a, b])).json()
    task = asyncio.create_task(_execute(run["id"]))
    for _ in range(100):
        if (await root.get(f"/api/runs/{run['id']}")).json()["items"][0]["status"] == "running":
            break
        await asyncio.sleep(0.05)
    assert (await root.post(f"/api/runs/{run['id']}/cancel")).status_code == 200
    assert await task == RunStatus.CANCELLED
    detail = (await root.get(f"/api/runs/{run['id']}")).json()
    # Bước đang chạy được hoàn tất, test sau không bắt đầu.
    assert detail["items"][1]["status"] == "cancelled" and detail["items"][1]["attempts"] == 0
    assert detail["cancelled"] == 1


async def test_private_network_blocked_and_unsupported_adapter(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url, private=False)
    health = await _case(root, pid, "Health", API_HEALTH)
    mac = await _case(root, pid, "Ứng dụng Mac", {"kind": "desktop_macos", "notes": "Mở ứng dụng"})
    run = (await _run(root, pid, eid, [health, mac])).json()
    assert await _execute(run["id"]) == RunStatus.BLOCKED
    items = (await root.get(f"/api/runs/{run['id']}")).json()["items"]
    assert items[0]["status"] == "blocked" and items[0]["error_type"] == "blocked_target"
    # Test desktop chỉ có mô tả thủ công: báo blocked, không bao giờ pass giả.
    assert items[1]["status"] == "blocked" and items[1]["error_type"] == "no_steps"
    adapters = {a["key"]: a for a in (await root.get("/api/adapters")).json()}
    assert adapters["desktop-macos"]["status"] == "experimental"
    assert adapters["api-httpx"]["status"] == "supported"


async def test_recover_stale_runs(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    cid = await _case(root, pid, "Health", API_HEALTH)
    run = (await _run(root, pid, eid, [cid])).json()
    async with get_sessionmaker()() as db:
        await db.execute(
            update(TestRun)
            .where(TestRun.id == uuid.UUID(run["id"]))
            .values(status=RunStatus.RUNNING, heartbeat_at=datetime.now(UTC) - timedelta(hours=2))
        )
        await db.commit()
    assert await RunExecutor(get_engine()).recover_stale_runs() == 1
    detail = (await root.get(f"/api/runs/{run['id']}")).json()
    assert detail["status"] == "error" and "heartbeat" in detail["error"]
    assert detail["items"][0]["status"] == "error"


async def test_run_access_control(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    cid = await _case(root, pid, "Health", API_HEALTH)
    await make_user("viewer@x.vn")
    await make_user("out@x.vn")
    assert (
        await root.post(
            f"/api/projects/{pid}/members", json={"email": "viewer@x.vn", "role": "viewer"}
        )
    ).status_code == 201
    viewer, outsider = await login_as("viewer@x.vn"), await login_as("out@x.vn")

    assert (await _run(viewer, pid, eid, [cid])).status_code == 403
    run = (await _run(root, pid, eid, [cid])).json()
    assert (await viewer.get(f"/api/runs/{run['id']}")).status_code == 200
    assert (await viewer.post(f"/api/runs/{run['id']}/cancel")).status_code == 403
    assert [r["id"] for r in (await viewer.get("/api/runs/active")).json()] == [run["id"]]

    await _execute(run["id"])
    item_id = (await root.get(f"/api/runs/{run['id']}")).json()["items"][0]["id"]
    for url in (f"/api/runs/{run['id']}", f"/api/run-items/{item_id}", f"/api/projects/{pid}/runs"):
        assert (await outsider.get(url)).status_code == 404, url
    assert (await outsider.post(f"/api/runs/{run['id']}/cancel")).status_code == 404
    assert (await outsider.get("/api/runs/active")).json() == []
    # Môi trường của dự án khác không được dùng.
    other_pid, other_eid = await setup_project(root, demo_url, key="KHAC")
    assert (await _run(root, pid, other_eid, [cid])).status_code == 422
    assert (await _run(root, other_pid, other_eid, [cid])).status_code == 422


@pytest.mark.skipif(
    not os.environ.get("OMNITEST_CHROMIUM_EXECUTABLE"),
    reason="Cần Chromium (OMNITEST_CHROMIUM_EXECUTABLE)",
)
async def test_web_run_saves_screenshot_artifact(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root = await _root(make_user, login_as)
    pid, eid = await setup_project(root, demo_url)
    web = {
        "kind": "web",
        "trace": "always",
        "steps": [
            {"name": "Mở", "action": "goto", "value": "/login"},
            {"name": "Tên", "action": "fill", "selector": "label=Tên đăng nhập", "value": "demo"},
            {
                "name": "Mật khẩu",
                "action": "fill",
                "selector": "label=Mật khẩu",
                "value": "{{DEMO_PASSWORD}}",
            },
            {"name": "Đăng nhập", "action": "click", "selector": 'role=button[name="Đăng nhập"]'},
            {"name": "Vào trang hàng", "action": "expect_url", "value": "/items"},
            {"name": "Chụp", "action": "screenshot"},
        ],
    }
    cid = await _case(root, pid, "Web đăng nhập", web)
    run = (await _run(root, pid, eid, [cid])).json()
    assert await _execute(run["id"]) == RunStatus.PASSED
    item_id = (await root.get(f"/api/runs/{run['id']}")).json()["items"][0]["id"]
    item = (await root.get(f"/api/run-items/{item_id}")).json()
    assert SECRET not in json.dumps(item, ensure_ascii=False)
    kinds = {a["kind"]: a for a in item["artifacts"]}
    assert {"screenshot", "trace"} <= set(kinds)
    shot = await root.get(f"/api/artifacts/{kinds['screenshot']['id']}")
    assert shot.status_code == 200 and shot.content.startswith(b"\x89PNG")
    await make_user("out@x.vn")
    outsider = await login_as("out@x.vn")
    assert (await outsider.get(f"/api/artifacts/{kinds['screenshot']['id']}")).status_code == 404
    # Trace ghi lại giá trị nhập vào form: secret phải được che trước khi lưu.
    trace = await root.get(f"/api/artifacts/{kinds['trace']['id']}")
    assert trace.status_code == 200
    with zipfile.ZipFile(io.BytesIO(trace.content)) as z:
        contents = {name: z.read(name) for name in z.namelist()}
    assert all(SECRET.encode() not in data for data in contents.values())
    # Trace thật có ghi giá trị đã nhập (đã bị thay bằng ***), nên kiểm tra trên có ý nghĩa.
    assert any(b"***" in data for data in contents.values())


def test_final_run_status() -> None:
    P, F, B, S, E, C = (
        RunStatus.PASSED,
        RunStatus.FAILED,
        RunStatus.BLOCKED,
        RunStatus.SKIPPED,
        RunStatus.ERROR,
        RunStatus.CANCELLED,
    )
    assert final_run_status([P, P], False) == P
    assert final_run_status([P, F, B], False) == F
    assert final_run_status([P, E], False) == F
    assert final_run_status([P, B], False) == B
    assert final_run_status([S, S], False) == S
    assert final_run_status([P, C], True) == C
    assert final_run_status([], False) == F
