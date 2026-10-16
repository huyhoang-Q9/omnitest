"""Kiểm tra IDOR: người ngoài dự án không truy cập được bất kỳ endpoint nào của dự án."""

import httpx
import pytest

from tests.conftest import LoginAs, MakeUser


@pytest.fixture
async def world(make_user: MakeUser, login_as: LoginAs) -> dict[str, object]:
    await make_user("root@x.vn", admin=True)
    await make_user("outsider@x.vn")
    root = await login_as("root@x.vn")
    pid = (await root.post("/api/projects", json={"key": "SEC", "name": "S"})).json()["id"]
    eid = (
        await root.post(
            f"/api/projects/{pid}/environments",
            json={"name": "Dev", "kind": "dev", "base_url": "https://a.vn"},
        )
    ).json()["id"]
    vid = (
        await root.post(f"/api/environments/{eid}/variables", json={"key": "K", "value": "v"})
    ).json()["id"]
    mid = (await root.get(f"/api/projects/{pid}/members")).json()[0]["id"]
    return {
        "pid": pid,
        "eid": eid,
        "vid": vid,
        "mid": mid,
        "outsider": await login_as("outsider@x.vn"),
    }


ENDPOINTS = [
    ("GET", "/api/projects/{pid}", None),
    ("PATCH", "/api/projects/{pid}", {"name": "x"}),
    ("POST", "/api/projects/{pid}/archive", None),
    ("POST", "/api/projects/{pid}/restore", None),
    ("GET", "/api/projects/{pid}/members", None),
    ("POST", "/api/projects/{pid}/members", {"email": "outsider@x.vn", "role": "admin"}),
    ("PATCH", "/api/projects/{pid}/members/{mid}", {"role": "viewer"}),
    ("DELETE", "/api/projects/{pid}/members/{mid}", None),
    ("GET", "/api/projects/{pid}/environments", None),
    (
        "POST",
        "/api/projects/{pid}/environments",
        {"name": "X", "kind": "dev", "base_url": "https://x.vn"},
    ),
    ("GET", "/api/projects/{pid}/audit-logs", None),
    ("GET", "/api/environments/{eid}", None),
    ("PATCH", "/api/environments/{eid}", {"name": "x"}),
    ("DELETE", "/api/environments/{eid}", None),
    ("GET", "/api/environments/{eid}/variables", None),
    ("POST", "/api/environments/{eid}/variables", {"key": "Z", "value": "z"}),
    ("PATCH", "/api/environments/{eid}/variables/{vid}", {"value": "z"}),
    ("DELETE", "/api/environments/{eid}/variables/{vid}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
async def test_outsider_gets_404(
    world: dict[str, object], method: str, path: str, body: object
) -> None:
    c = world["outsider"]
    assert isinstance(c, httpx.AsyncClient)
    url = path.format(**{k: v for k, v in world.items() if isinstance(v, str)})
    r = await c.request(method, url, json=body)
    assert r.status_code == 404, f"{method} {url} -> {r.status_code}"


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
async def test_anonymous_gets_401(
    world: dict[str, object], client: httpx.AsyncClient, method: str, path: str, body: object
) -> None:
    url = path.format(**{k: v for k, v in world.items() if isinstance(v, str)})
    assert (await client.request(method, url, json=body)).status_code == 401


async def test_system_admin_only_endpoints(world: dict[str, object]) -> None:
    c = world["outsider"]
    assert isinstance(c, httpx.AsyncClient)
    assert (await c.get("/api/users")).status_code == 403
    assert (
        await c.post(
            "/api/users", json={"email": "n@x.vn", "full_name": "n", "password": "Hople-Pass-2026"}
        )
    ).status_code == 403
    assert (await c.get("/api/users/lookup", params={"q": "root"})).status_code == 403
