import uuid

from omnitest_worker.executor import RunExecutor

from omnitest_api.db import get_engine
from tests.conftest import LoginAs, MakeUser
from tests.integration.phase3_helpers import API_HEALTH, case_body, setup_project


async def test_dashboard_counts_only_visible_projects(
    make_user: MakeUser, login_as: LoginAs
) -> None:
    await make_user("root@x.vn", admin=True)
    await make_user("u@x.vn")
    root = await login_as("root@x.vn")
    p1 = (await root.post("/api/projects", json={"key": "AA", "name": "A"})).json()["id"]
    await root.post("/api/projects", json={"key": "BB", "name": "B"})
    await root.post(f"/api/projects/{p1}/members", json={"email": "u@x.vn", "role": "tester"})
    await root.post(
        f"/api/projects/{p1}/environments",
        json={"name": "Dev", "kind": "dev", "base_url": "https://a.vn"},
    )

    u = await login_as("u@x.vn")
    d = (await u.get("/api/dashboard")).json()
    assert d["projects"] == 1 and d["environments"] == 1 and d["members"] == 2
    # Chưa có lần chạy nào: tỷ lệ pass là null (không hiển thị 0% giả).
    assert d["test_cases"] == 0 and d["runs_total"] == 0 and d["pass_rate"] is None
    assert len(d["daily"]) == d["period_days"] == 14
    assert d["recent_runs"] == [] and d["attention"] == []
    actions = {a["action"] for a in d["recent_activity"]}
    assert "project.create" in actions
    # Không thấy hoạt động của dự án BB mà mình không tham gia.
    assert all(a["project_id"] in (None, p1) for a in d["recent_activity"])
    assert (await root.get("/api/dashboard")).json()["projects"] == 2


async def test_project_audit_log_requires_manager(make_user: MakeUser, login_as: LoginAs) -> None:
    await make_user("root@x.vn", admin=True)
    await make_user("v@x.vn")
    root = await login_as("root@x.vn")
    pid = (await root.post("/api/projects", json={"key": "AA", "name": "A"})).json()["id"]
    await root.post(f"/api/projects/{pid}/members", json={"email": "v@x.vn", "role": "viewer"})
    v = await login_as("v@x.vn")
    assert (await v.get(f"/api/projects/{pid}/audit-logs")).status_code == 403
    logs = (await root.get(f"/api/projects/{pid}/audit-logs")).json()
    assert logs["total"] >= 2


async def test_dashboard_run_statistics_and_attention(
    make_user: MakeUser, login_as: LoginAs, demo_url: str
) -> None:
    await make_user("root@x.vn", admin=True)
    await make_user("out@x.vn")
    root = await login_as("root@x.vn")
    pid, eid = await setup_project(root, demo_url)
    failing = {
        "kind": "api",
        "steps": [
            {
                "name": "Không token",
                "url": "/api/items",
                "assertions": [{"type": "status", "equals": 200}],
            }
        ],
    }
    ok = (
        await root.post(f"/api/projects/{pid}/test-cases", json=case_body("Health", API_HEALTH))
    ).json()
    bad = (
        await root.post(f"/api/projects/{pid}/test-cases", json=case_body("Lỗi", failing))
    ).json()
    run = (
        await root.post(
            f"/api/projects/{pid}/runs",
            json={"environment_id": eid, "test_case_ids": [ok["id"], bad["id"]]},
        )
    ).json()
    await RunExecutor(get_engine()).execute_run(uuid.UUID(run["id"]))

    d = (await root.get("/api/dashboard")).json()
    assert d["test_cases"] == 2 and d["runs_total"] == 1 and d["active_runs"] == 0
    assert d["item_totals"]["passed"] == 1 and d["item_totals"]["failed"] == 1
    assert d["pass_rate"] == 50.0
    assert d["daily"][-1]["passed"] == 1 and d["daily"][-1]["failed"] == 1
    assert [r["id"] for r in d["recent_runs"]] == [run["id"]]
    assert [a["code"] for a in d["attention"]] == [bad["code"]]
    # Người ngoài dự án không thấy số liệu của dự án này.
    out = (await (await login_as("out@x.vn")).get("/api/dashboard")).json()
    assert out["runs_total"] == 0 and out["attention"] == [] and out["recent_runs"] == []
