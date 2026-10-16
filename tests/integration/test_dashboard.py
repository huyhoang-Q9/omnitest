from tests.conftest import LoginAs, MakeUser


async def test_dashboard_counts_only_visible_projects_and_no_fake_stats(
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
    # Chưa có chức năng test case/run: trả null kèm ghi chú, không trả số 0 giả.
    assert d["test_cases"] == {"value": None, "available": False, "note": d["test_cases"]["note"]}
    assert d["test_cases"]["note"]
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
