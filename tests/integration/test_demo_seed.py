"""Seed demo rồi chạy thật toàn bộ test mẫu với demo-target: bộ mẫu phải pass, không pass giả."""

import os
import uuid

import pytest
from omnitest_worker.executor import RunExecutor

from omnitest_api.db import get_engine
from omnitest_api.services.demo_seed import CASES, SeedError, seed_demo
from tests.conftest import LoginAs, MakeUser


async def test_seed_demo_and_run_all(make_user: MakeUser, login_as: LoginAs, demo_url: str) -> None:
    await make_user("root@x.vn", admin=True)
    await make_user("u@x.vn")
    with pytest.raises(SeedError):
        await seed_demo("u@x.vn", demo_url)
    result = await seed_demo("root@x.vn", demo_url)
    assert result["test_cases"] == len(CASES)
    # Không ghi đè dự án đã có.
    with pytest.raises(SeedError):
        await seed_demo("root@x.vn", demo_url)

    root = await login_as("root@x.vn")
    pid, eid = result["project_id"], result["environment_id"]
    suites = {s["name"]: s for s in (await root.get(f"/api/projects/{pid}/suites")).json()}
    assert suites["Smoke"]["case_count"] == 4
    # Phiên tạm của lệnh seed đã bị xóa: chỉ còn phiên đăng nhập vừa tạo.
    me = await root.get("/api/auth/me")
    assert me.status_code == 200

    if os.environ.get("OMNITEST_CHROMIUM_EXECUTABLE"):
        scope: dict[str, object] = {"suite_id": suites["Hồi quy đầy đủ"]["id"]}
        expected_total = len(CASES)
    else:
        # Không có trình duyệt: chỉ chạy test API.
        cases = (
            await root.get(f"/api/projects/{pid}/test-cases", params={"test_type": "api"})
        ).json()
        scope = {"test_case_ids": [c["id"] for c in cases["items"]]}
        expected_total = len(scope["test_case_ids"])  # type: ignore[arg-type]
    r = await root.post(
        f"/api/projects/{pid}/runs", json={"environment_id": eid, "confirm": True, **scope}
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    await RunExecutor(get_engine()).execute_run(uuid.UUID(run_id))
    detail = (await root.get(f"/api/runs/{run_id}")).json()
    failures = [
        (i["code"], i["title"], i["error"]) for i in detail["items"] if i["status"] != "passed"
    ]
    assert failures == []
    assert detail["status"] == "passed" and detail["passed"] == expected_total
