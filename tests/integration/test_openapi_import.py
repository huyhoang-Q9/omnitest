"""Import OpenAPI qua API: xem trước không ghi gì, tạo test Nháp, bỏ trùng, phân quyền, giới hạn kích thước.
Test sinh ra được chạy thật với demo-target (dùng chính tài liệu OpenAPI của demo-target)."""

import json
import uuid

from omnitest_demo_target.app import app as demo_app
from omnitest_worker.executor import RunExecutor
from sqlalchemy import func, select

from omnitest_api.db import get_engine, get_sessionmaker
from omnitest_api.models import AuditLog, TestCase
from tests.conftest import LoginAs, MakeUser
from tests.integration.phase3_helpers import setup_project


def _file(data: bytes, name: str = "openapi.json") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, data, "application/json")}


async def _count_cases(pid: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.scalar(select(func.count()).where(TestCase.project_id == uuid.UUID(pid))) or 0
        )


async def test_import_demo_openapi_and_run_generated_cases(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    await make_user("root@x.vn", admin=True)
    root = await login_as("root@x.vn")
    pid, eid = await setup_project(root, demo_url)
    spec = json.dumps(demo_app.openapi()).encode()
    url = f"/api/projects/{pid}/test-cases/import-openapi"

    preview = await root.post(url, files=_file(spec))
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p["dry_run"] is True and p["created"] == p["operations"] and p["operations"] >= 8
    ops = {f"{i['method']} {i['path']}": i for i in p["items"]}
    assert ops["DELETE /api/items/{item_id}"]["side_effect"] is True
    assert ops["GET /api/health"]["side_effect"] is False
    assert ops["GET /api/redirect"]["variables"] == ["TO"]
    assert await _count_cases(pid) == 0  # xem trước không ghi gì

    done = (
        await root.post(url, params={"dry_run": "false", "tag": "Demo"}, files=_file(spec))
    ).json()
    assert done["created"] == p["operations"] and len(done["created_codes"]) == p["operations"]
    assert await _count_cases(pid) == p["operations"]
    again = (await root.post(url, params={"dry_run": "false"}, files=_file(spec))).json()
    assert again["created"] == 0 and again["skipped_duplicates"] == p["operations"]
    assert await _count_cases(pid) == p["operations"]

    cases = (await root.get(f"/api/projects/{pid}/test-cases", params={"tag": "openapi"})).json()
    by_title = {c["title"].split(":")[0]: c for c in cases["items"]}
    health = by_title["GET /api/health"]
    assert health["status"] == "draft" and set(health["tags"]) == {"openapi", "demo"}
    redirect = by_title["GET /api/redirect"]

    r = await root.post(
        f"/api/projects/{pid}/runs",
        json={"environment_id": eid, "test_case_ids": [health["id"], redirect["id"]]},
    )
    assert r.status_code == 201, r.text
    await RunExecutor(get_engine()).execute_run(uuid.UUID(r.json()["id"]))
    detail = (await root.get(f"/api/runs/{r.json()['id']}")).json()
    statuses = {i["code"]: (i["status"], i["error_type"]) for i in detail["items"]}
    assert statuses[health["code"]] == ("passed", None)
    # Thiếu biến TO: báo lỗi rõ ràng, không đoán giá trị.
    assert statuses[redirect["code"]] == ("error", "missing_variable")

    async with get_sessionmaker()() as s:
        n = await s.scalar(
            select(func.count()).where(AuditLog.action == "test_case.import_openapi")
        )
    assert n == 2


async def test_import_openapi_permissions_and_limits(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    await make_user("root@x.vn", admin=True)
    await make_user("tester@x.vn")
    root = await login_as("root@x.vn")
    pid, _ = await setup_project(root, demo_url)
    await root.post(f"/api/projects/{pid}/members", json={"email": "tester@x.vn", "role": "tester"})
    url = f"/api/projects/{pid}/test-cases/import-openapi"
    spec = json.dumps(demo_app.openapi()).encode()

    tester = await login_as("tester@x.vn")
    assert (await tester.post(url, files=_file(spec))).status_code == 403
    big = b'{"openapi": "3.0.0", "x": "' + b"a" * (2 * 1024 * 1024) + b'"}'
    assert (await root.post(url, files=_file(big))).status_code == 413
    bad = await root.post(url, files=_file(b'{"swagger": "2.0", "paths": {}}'))
    assert bad.status_code == 422 and "Swagger 2.0" in bad.json()["detail"]
    bomb = b"openapi: 3.0.0\na: &a [x]\nb: [*a]\npaths: {}\n"
    assert (await root.post(url, files=_file(bomb, "x.yaml"))).status_code == 422
