import httpx
from sqlalchemy import select

from omnitest_api.db import get_sessionmaker
from omnitest_api.models import AuditLog
from tests.conftest import PASSWORD, LoginAs, MakeUser


async def test_login_sets_secure_session_cookie(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("a@x.vn")
    r = await client.post("/api/auth/login", json={"email": "A@x.vn", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["email"] == "a@x.vn"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "a@x.vn"
    assert "password_hash" not in me.text


async def test_wrong_password_and_unknown_email_same_message(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("a@x.vn")
    r1 = await client.post(
        "/api/auth/login", json={"email": "a@x.vn", "password": "Sai-mat-khau-1"}
    )
    r2 = await client.post(
        "/api/auth/login", json={"email": "khongco@x.vn", "password": "Sai-mat-khau-1"}
    )
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


async def test_lockout_after_repeated_failures(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("a@x.vn")
    for _ in range(5):
        r = await client.post(
            "/api/auth/login", json={"email": "a@x.vn", "password": "Sai-mat-khau-1"}
        )
        assert r.status_code == 401
    # Đúng mật khẩu nhưng đang bị khóa.
    r = await client.post("/api/auth/login", json={"email": "a@x.vn", "password": PASSWORD})
    assert r.status_code == 429
    async with get_sessionmaker()() as db:
        actions = list(await db.scalars(select(AuditLog.action)))
    assert actions.count("auth.login_failed") == 5
    assert "auth.login_locked" in actions


async def test_inactive_user_cannot_login(client: httpx.AsyncClient, make_user: MakeUser) -> None:
    await make_user("off@x.vn", active=False)
    r = await client.post("/api/auth/login", json={"email": "off@x.vn", "password": PASSWORD})
    assert r.status_code == 401


async def test_me_requires_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_invalidates_server_session(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("a@x.vn")
    await client.post("/api/auth/login", json={"email": "a@x.vn", "password": PASSWORD})
    token = client.cookies.get("omnitest_session")
    assert token
    assert (await client.post("/api/auth/logout")).status_code == 204
    # Dùng lại token cũ: server đã xóa phiên nên phải bị từ chối.
    client.cookies.set("omnitest_session", token)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_system_admin_creates_user_with_password_policy(
    make_user: MakeUser, login_as: LoginAs
) -> None:
    await make_user("root@x.vn", admin=True)
    c = await login_as("root@x.vn")
    weak = await c.post("/api/users", json={"email": "u@x.vn", "full_name": "U", "password": "123"})
    assert weak.status_code == 422
    ok = await c.post(
        "/api/users", json={"email": "u@x.vn", "full_name": "U", "password": "Hople-Pass-2026"}
    )
    assert ok.status_code == 201
    dup = await c.post(
        "/api/users", json={"email": "U@x.vn", "full_name": "U", "password": "Hople-Pass-2026"}
    )
    assert dup.status_code == 409


async def test_login_with_internal_domain(client: httpx.AsyncClient, make_user: MakeUser) -> None:
    """Hồi quy: tên miền .local từng bị từ chối với lỗi 422 nên không đăng nhập được."""
    await make_user("admin@omnitest.local")
    r = await client.post(
        "/api/auth/login", json={"email": "Admin@OmniTest.local", "password": PASSWORD}
    )
    assert r.status_code == 200
