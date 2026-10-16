import httpx

from tests.conftest import LoginAs, MakeUser


async def _setup(make_user: MakeUser, login_as: LoginAs) -> tuple[httpx.AsyncClient, str]:
    await make_user("root@x.vn", admin=True)
    root = await login_as("root@x.vn")
    r = await root.post(
        "/api/projects", json={"key": "shop", "name": "Cửa hàng", "description": "Demo"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["key"] == "SHOP" and r.json()["my_role"] == "admin"
    return root, r.json()["id"]


async def test_only_system_admin_creates_projects(make_user: MakeUser, login_as: LoginAs) -> None:
    await make_user("u@x.vn")
    c = await login_as("u@x.vn")
    r = await c.post("/api/projects", json={"key": "AB", "name": "x"})
    assert r.status_code == 403


async def test_duplicate_key_conflict(make_user: MakeUser, login_as: LoginAs) -> None:
    root, _ = await _setup(make_user, login_as)
    assert (await root.post("/api/projects", json={"key": "SHOP", "name": "y"})).status_code == 409


async def test_members_roles_and_visibility(make_user: MakeUser, login_as: LoginAs) -> None:
    root, pid = await _setup(make_user, login_as)
    await make_user("viewer@x.vn")
    await make_user("manager@x.vn")
    await make_user("outsider@x.vn")
    assert (
        await root.post(
            f"/api/projects/{pid}/members", json={"email": "viewer@x.vn", "role": "viewer"}
        )
    ).status_code == 201
    assert (
        await root.post(
            f"/api/projects/{pid}/members", json={"email": "manager@x.vn", "role": "manager"}
        )
    ).status_code == 201
    assert (
        await root.post(
            f"/api/projects/{pid}/members", json={"email": "viewer@x.vn", "role": "tester"}
        )
    ).status_code == 409

    viewer = await login_as("viewer@x.vn")
    manager = await login_as("manager@x.vn")
    outsider = await login_as("outsider@x.vn")

    assert (await outsider.get("/api/projects")).json()["total"] == 0
    assert (await outsider.get(f"/api/projects/{pid}")).status_code == 404
    lst = (await viewer.get("/api/projects")).json()
    assert lst["total"] == 1 and lst["items"][0]["my_role"] == "viewer"
    assert lst["items"][0]["member_count"] == 3

    assert (await viewer.patch(f"/api/projects/{pid}", json={"name": "Đổi"})).status_code == 403
    r = await manager.patch(f"/api/projects/{pid}", json={"name": "Đổi tên"})
    assert r.status_code == 200 and r.json()["name"] == "Đổi tên"
    # Manager không quản lý thành viên.
    assert (
        await manager.post(
            f"/api/projects/{pid}/members", json={"email": "outsider@x.vn", "role": "viewer"}
        )
    ).status_code == 403


async def test_last_admin_cannot_be_removed_or_demoted(
    make_user: MakeUser, login_as: LoginAs
) -> None:
    root, pid = await _setup(make_user, login_as)
    members = (await root.get(f"/api/projects/{pid}/members")).json()
    admin_member = members[0]["id"]
    assert (
        await root.patch(f"/api/projects/{pid}/members/{admin_member}", json={"role": "viewer"})
    ).status_code == 409
    assert (await root.delete(f"/api/projects/{pid}/members/{admin_member}")).status_code == 409


async def test_archive_makes_project_read_only_and_restore(
    make_user: MakeUser, login_as: LoginAs
) -> None:
    root, pid = await _setup(make_user, login_as)
    assert (await root.post(f"/api/projects/{pid}/archive")).json()["is_archived"] is True
    assert (await root.patch(f"/api/projects/{pid}", json={"name": "x"})).status_code == 409
    env = await root.post(
        f"/api/projects/{pid}/environments",
        json={"name": "Dev", "kind": "dev", "base_url": "https://a.vn"},
    )
    assert env.status_code == 409
    assert (await root.get("/api/projects")).json()["total"] == 0
    assert (await root.get("/api/projects", params={"include_archived": True})).json()["total"] == 1
    assert (await root.post(f"/api/projects/{pid}/restore")).json()["is_archived"] is False


async def test_search_and_pagination(make_user: MakeUser, login_as: LoginAs) -> None:
    await make_user("root@x.vn", admin=True)
    root = await login_as("root@x.vn")
    for i in range(5):
        await root.post("/api/projects", json={"key": f"P{i}X", "name": f"Dự án {i}"})
    await root.post("/api/projects", json={"key": "HR", "name": "Nhân sự"})
    page = (await root.get("/api/projects", params={"page_size": 2, "page": 2})).json()
    assert page["total"] == 6 and len(page["items"]) == 2
    found = (await root.get("/api/projects", params={"q": "nhân"})).json()
    assert [p["key"] for p in found["items"]] == ["HR"]
