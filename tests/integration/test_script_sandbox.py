"""Script code qua API và worker: phân quyền (chỉ Admin dự án, dự án phải bật), xác nhận khi chạy, chặn khi máy
chủ hoặc dự án tắt, và một lần chạy thật trong container sandbox (cần Docker và image sandbox)."""

import uuid
from typing import Any

import pytest
from omnitest_worker.executor import RunExecutor
from sqlalchemy import select

from omnitest_api.config import get_settings
from omnitest_api.db import get_engine, get_sessionmaker
from omnitest_api.models import Artifact, AuditLog, RunStatus, TestRunItem
from tests.adapters.test_sandbox_adapter import docker
from tests.conftest import LoginAs, MakeUser
from tests.integration.phase3_helpers import case_body, setup_project

SECRET = "Demo@123"  # giá trị biến secret DEMO_PASSWORD do setup_project tạo
SCRIPT: dict[str, Any] = {
    "kind": "script",
    "files": {
        "test_demo.py": (
            "import os\n"
            "def test_bien_moi_truong():\n"
            "    print('mat khau', os.environ['OMNITEST_VAR_DEMO_PASSWORD'])\n"
            "    assert os.environ['OMNITEST_VAR_DEMO_PASSWORD']\n"
        )
    },
}


async def _setup(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> tuple:  # type: ignore[type-arg]
    await make_user("root@x.vn", admin=True)
    await make_user("manager@x.vn")
    await make_user("tester@x.vn")
    root = await login_as("root@x.vn")
    pid, eid = await setup_project(root, demo_url)
    for email, role in (("manager@x.vn", "manager"), ("tester@x.vn", "tester")):
        r = await root.post(f"/api/projects/{pid}/members", json={"email": email, "role": role})
        assert r.status_code == 201
    return root, pid, eid


def _executor(sandbox: bool) -> RunExecutor:
    settings = get_settings().model_copy(update={"sandbox_enabled": sandbox})
    return RunExecutor(get_engine(), settings=settings)


async def _item(run_id: str) -> TestRunItem:
    async with get_sessionmaker()() as db:
        item = await db.scalar(select(TestRunItem).where(TestRunItem.run_id == uuid.UUID(run_id)))
        assert item is not None
        return item


async def test_only_project_admin_with_script_enabled_can_write_scripts(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root, pid, _ = await _setup(make_user, login_as, demo_url)
    manager = await login_as("manager@x.vn")
    url = f"/api/projects/{pid}/test-cases"

    r = await root.post(url, json=case_body("Script", SCRIPT))
    assert r.status_code == 403 and "chưa bật" in r.json()["detail"]
    assert (
        await manager.patch(f"/api/projects/{pid}", json={"script_enabled": True})
    ).status_code == 403
    r = await root.patch(f"/api/projects/{pid}", json={"script_enabled": True})
    assert r.status_code == 200 and r.json()["script_enabled"] is True

    r = await manager.post(url, json=case_body("Script", SCRIPT))
    assert r.status_code == 403 and "Admin" in r.json()["detail"]
    r = await root.post(url, json=case_body("Script", SCRIPT))
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["side_effect"] is True and case["step_count"] == 1

    # Manager không sửa, không nhân bản, không đổi test thường thành script.
    r = await manager.patch(
        f"/api/test-cases/{case['id']}", json={"version": case["version"], "title": "Đổi"}
    )
    assert r.status_code == 403
    assert (await manager.post(f"/api/test-cases/{case['id']}/duplicate")).status_code == 403
    api_case = (
        await manager.post(
            url,
            json=case_body(
                "API",
                {"kind": "api", "steps": [{"name": "H", "url": "/api/health"}]},
            ),
        )
    ).json()
    r = await manager.patch(
        f"/api/test-cases/{api_case['id']}",
        json={"version": api_case["version"], "test_type": "script", "definition": SCRIPT},
    )
    assert r.status_code == 403

    async with get_sessionmaker()() as db:
        toggles = list(
            await db.scalars(select(AuditLog).where(AuditLog.action == "project.update"))
        )
    assert any(a.details.get("script_enabled") is True for a in toggles)


async def test_import_cannot_smuggle_scripts(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root, pid, _ = await _setup(make_user, login_as, demo_url)
    await root.patch(f"/api/projects/{pid}", json={"script_enabled": True})
    await root.post(f"/api/projects/{pid}/test-cases", json=case_body("Script", SCRIPT))
    exported = await root.get(f"/api/projects/{pid}/test-cases/export?format=csv")
    assert exported.status_code == 200
    manager = await login_as("manager@x.vn")
    r = await manager.post(
        f"/api/projects/{pid}/test-cases/import?dry_run=false",
        files={"file": ("tc.csv", exported.content, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True and any("Admin" in e["message"] for e in body["errors"])


async def test_run_needs_confirmation_and_is_blocked_when_disabled(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    root, pid, eid = await _setup(make_user, login_as, demo_url)
    await root.patch(f"/api/projects/{pid}", json={"script_enabled": True})
    cid = (
        await root.post(f"/api/projects/{pid}/test-cases", json=case_body("Script", SCRIPT))
    ).json()["id"]
    tester = await login_as("tester@x.vn")
    run_body = {"environment_id": eid, "test_case_ids": [cid]}

    r = await tester.post(f"/api/projects/{pid}/runs", json=run_body)
    assert r.status_code == 409
    assert any("sandbox" in x for x in r.json()["detail"]["reasons"])

    # Máy chủ chưa bật sandbox: Bị chặn, không thử lại, không bao giờ đạt.
    run = (
        await tester.post(f"/api/projects/{pid}/runs", json={**run_body, "confirm": True})
    ).json()
    assert await _executor(False).execute_run(uuid.UUID(run["id"])) == RunStatus.BLOCKED
    item = await _item(run["id"])
    assert item.error_type == "sandbox_disabled" and item.attempts == 1

    # Admin tắt script code sau khi đã tạo: lần chạy cũng bị chặn.
    await root.patch(f"/api/projects/{pid}", json={"script_enabled": False})
    run = (
        await tester.post(f"/api/projects/{pid}/runs", json={**run_body, "confirm": True})
    ).json()
    assert await _executor(True).execute_run(uuid.UUID(run["id"])) == RunStatus.BLOCKED
    assert (await _item(run["id"])).error_type == "script_disabled"

    adapters = (await tester.get("/api/adapters")).json()
    script_adapter = next(a for a in adapters if "script" in a["test_kinds"])
    assert script_adapter["environment_ok"] is False


@docker
async def test_real_sandbox_run_saves_masked_evidence(
    make_user: MakeUser, login_as: LoginAs, demo_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pid, eid = await _setup(make_user, login_as, demo_url)
    await root.patch(f"/api/projects/{pid}", json={"script_enabled": True})
    cid = (
        await root.post(f"/api/projects/{pid}/test-cases", json=case_body("Script", SCRIPT))
    ).json()["id"]
    run = (
        await root.post(
            f"/api/projects/{pid}/runs",
            json={"environment_id": eid, "test_case_ids": [cid], "confirm": True},
        )
    ).json()
    assert await _executor(True).execute_run(uuid.UUID(run["id"])) == RunStatus.PASSED
    item = (await root.get(f"/api/runs/{run['id']}")).json()["items"][0]
    detail = (await root.get(f"/api/run-items/{item['id']}")).json()
    assert [s["name"] for s in detail["steps"]] == ["test_demo::test_bien_moi_truong"]
    log_art = next(a for a in detail["artifacts"] if a["filename"] == "pytest-output.txt")
    text = (await root.get(f"/api/artifacts/{log_art['id']}")).text
    assert "mat khau ***" in text and SECRET not in text
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(Artifact).where(Artifact.run_id == uuid.UUID(run["id"])))
