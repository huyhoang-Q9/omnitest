"""Trợ lý AI qua API, dùng test double cho nhà cung cấp (xem tests/ai/fakes.py): AI tắt thì báo rõ, dự án phải
được Admin bật, kết quả không tự lưu, dữ liệu gửi đi không chứa secret, audit không ghi nội dung."""

import json
import uuid

import pytest
from omnitest_worker.executor import RunExecutor
from sqlalchemy import func, select

from omnitest_api.db import get_engine, get_sessionmaker
from omnitest_api.models import AuditLog, TestCase
from omnitest_api.routers import ai as ai_router
from tests.ai.fakes import API_DRAFT, FakeAnthropic
from tests.conftest import LoginAs, MakeUser
from tests.integration.phase3_helpers import case_body, setup_project

SECRET = "Demo@123"
REQUIREMENT = "Kiểm tra API health của ứng dụng kho hàng mini"


async def _setup(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> tuple:  # type: ignore[type-arg]
    await make_user("root@x.vn", admin=True)
    await make_user("manager@x.vn")
    await make_user("viewer@x.vn")
    root = await login_as("root@x.vn")
    pid, eid = await setup_project(root, demo_url)
    for email, role in (("manager@x.vn", "manager"), ("viewer@x.vn", "viewer")):
        r = await root.post(f"/api/projects/{pid}/members", json={"email": email, "role": role})
        assert r.status_code == 201
    return root, pid, eid


async def test_ai_disabled_by_default(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root, pid, _ = await _setup(make_user, login_as, demo_url)
    status = (await root.get("/api/ai/status")).json()
    assert status == {"configured": False, "provider": "none", "model": None}
    r = await root.post(
        f"/api/projects/{pid}/ai/suggest-test-cases", json={"requirement": REQUIREMENT}
    )
    assert r.status_code == 503 and "chưa được cấu hình" in r.json()["detail"]
    # Mọi chức năng khác vẫn chạy bình thường khi AI tắt.
    assert (await root.get(f"/api/projects/{pid}/test-cases")).status_code == 200


async def test_project_toggle_requires_project_admin(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root, pid, _ = await _setup(make_user, login_as, demo_url)
    manager = await login_as("manager@x.vn")
    r = await manager.patch(f"/api/projects/{pid}", json={"ai_enabled": True})
    assert r.status_code == 403
    assert (
        await manager.patch(f"/api/projects/{pid}", json={"name": "Đổi tên"})
    ).status_code == 200
    r = await root.patch(f"/api/projects/{pid}", json={"ai_enabled": True})
    assert r.status_code == 200 and r.json()["ai_enabled"] is True


async def test_suggest_returns_drafts_without_saving(
    make_user: MakeUser, login_as: LoginAs, demo_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pid, _ = await _setup(make_user, login_as, demo_url)
    fake = FakeAnthropic({"assumptions": ["Không cần đăng nhập"], "test_cases": [API_DRAFT]})
    monkeypatch.setattr(ai_router, "get_provider", fake.provider)
    url = f"/api/projects/{pid}/ai/suggest-test-cases"

    r = await root.post(url, json={"requirement": REQUIREMENT})
    assert r.status_code == 403 and "chưa bật AI" in r.json()["detail"]
    assert fake.requests == []  # không gửi gì ra ngoài khi dự án chưa bật
    await root.patch(f"/api/projects/{pid}", json={"ai_enabled": True})

    viewer = await login_as("viewer@x.vn")
    assert (await viewer.post(url, json={"requirement": REQUIREMENT})).status_code == 403
    manager = await login_as("manager@x.vn")
    r = await manager.post(url, json={"requirement": REQUIREMENT, "test_type": "api", "count": 3})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["drafts"][0]["valid"] is True and res["drafts"][0]["assumptions"]
    assert res["model"] == "claude-test-double"
    async with get_sessionmaker()() as s:
        assert await s.scalar(select(func.count()).select_from(TestCase)) == 0
        logs = list(
            await s.scalars(select(AuditLog).where(AuditLog.action == "ai.suggest_test_cases"))
        )
    assert len(logs) == 1 and logs[0].details["usage"] == {"input": 123, "output": 45}
    assert REQUIREMENT not in json.dumps(logs[0].details, ensure_ascii=False)

    # Người dùng duyệt: lưu qua API tạo test case thông thường, trạng thái Nháp.
    d = res["drafts"][0]
    saved = await manager.post(
        f"/api/projects/{pid}/test-cases",
        json={
            "title": d["title"],
            "test_type": d["test_type"],
            "definition": d["definition"],
            "tags": [*d["tags"], "ai"],
            "status": "draft",
        },
    )
    assert saved.status_code == 201, saved.text

    fake.status = 500
    r = await manager.post(url, json={"requirement": REQUIREMENT})
    assert r.status_code == 502 and "đang lỗi" in r.json()["detail"]


async def test_analyze_failure_sends_masked_context_only(
    make_user: MakeUser, login_as: LoginAs, demo_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pid, eid = await _setup(make_user, login_as, demo_url)
    await root.patch(f"/api/projects/{pid}", json={"ai_enabled": True})
    failing = {
        "kind": "api",
        "steps": [
            {
                "name": "Đăng nhập sai chỗ",
                "method": "POST",
                "url": "/api/login",
                "body_type": "json",
                "body": {"username": "demo", "password": "{{DEMO_PASSWORD}}"},
                "assertions": [{"type": "status", "equals": 418}],
            }
        ],
    }
    health = {"kind": "api", "steps": [{"name": "h", "url": "/api/health"}]}
    ids = []
    for title, d in (("Lỗi", failing), ("Đạt", health)):
        r = await root.post(f"/api/projects/{pid}/test-cases", json=case_body(title, d))
        ids.append(r.json()["id"])
    run = (
        await root.post(
            f"/api/projects/{pid}/runs",
            json={"environment_id": eid, "test_case_ids": ids, "confirm": True},
        )
    ).json()
    await RunExecutor(get_engine()).execute_run(uuid.UUID(run["id"]))
    items = (await root.get(f"/api/runs/{run['id']}")).json()["items"]
    bad_item, ok_item = items[0]["id"], items[1]["id"]

    fake = FakeAnthropic(
        {
            "summary": "Sai mã mong đợi",
            "probable_cause": "Assertion mong đợi 418 nhưng ứng dụng trả 200",
            "category": "test_script",
            "confidence": "high",
            "evidence": ["Bước 1"],
            "suggestions": ["Sửa assertion thành 200"],
            "assumptions": [],
        }
    )
    monkeypatch.setattr(ai_router, "get_provider", fake.provider)
    r = await root.post(f"/api/run-items/{bad_item}/ai/analyze")
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "test_script"
    sent = fake.sent_body()["messages"][0]["content"]
    assert "Đăng nhập sai chỗ" in sent and "{{DEMO_PASSWORD}}" in sent
    assert SECRET not in sent  # mật khẩu đã che trong log, không gửi giá trị biến

    assert (await root.post(f"/api/run-items/{ok_item}/ai/analyze")).status_code == 422
    viewer = await login_as("viewer@x.vn")
    assert (await viewer.post(f"/api/run-items/{bad_item}/ai/analyze")).status_code == 403
    await make_user("out@x.vn")
    outsider = await login_as("out@x.vn")
    assert (await outsider.post(f"/api/run-items/{bad_item}/ai/analyze")).status_code == 404
