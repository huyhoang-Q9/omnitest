import logging

import httpx
import pytest

from omnitest_api.main import create_app
from tests.conftest import PASSWORD, LoginAs, MakeUser


async def test_mutation_without_csrf_header_rejected(make_user: MakeUser) -> None:
    await make_user("a@x.vn")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as c:
        r = await c.post("/api/auth/login", json={"email": "a@x.vn", "password": PASSWORD})
        assert r.status_code == 403
        assert (await c.get("/api/health")).status_code == 200


async def test_security_headers(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


async def test_secret_value_not_in_logs(
    make_user: MakeUser, login_as: LoginAs, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "LogLeak-Should-Not-Appear-77"
    caplog.set_level(logging.DEBUG)
    await make_user("root@x.vn", admin=True)
    root = await login_as("root@x.vn")
    pid = (await root.post("/api/projects", json={"key": "LG", "name": "L"})).json()["id"]
    eid = (
        await root.post(
            f"/api/projects/{pid}/environments",
            json={"name": "Dev", "kind": "dev", "base_url": "https://a.vn"},
        )
    ).json()["id"]
    await root.post(
        f"/api/environments/{eid}/variables", json={"key": "PW", "value": secret, "is_secret": True}
    )
    assert secret not in caplog.text
    assert PASSWORD not in caplog.text


async def test_docs_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from omnitest_api.config import get_settings

    monkeypatch.setenv("OMNITEST_ENV", "production")
    get_settings.cache_clear()
    try:
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            assert (await c.get("/api/docs")).status_code == 404
            assert (await c.get("/api/openapi.json")).status_code == 404
    finally:
        monkeypatch.setenv("OMNITEST_ENV", "test")
        get_settings.cache_clear()
