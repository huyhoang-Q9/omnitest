import uuid

from sqlalchemy import select

from omnitest_api.db import get_sessionmaker
from omnitest_api.models import AuditLog, EnvironmentVariable
from tests.conftest import LoginAs, MakeUser

SECRET = "SieuBiMat-9f8e7d6c"


async def _project_with_manager(make_user: MakeUser, login_as: LoginAs):  # type: ignore[no-untyped-def]
    await make_user("root@x.vn", admin=True)
    await make_user("manager@x.vn")
    await make_user("viewer@x.vn")
    root = await login_as("root@x.vn")
    pid = (await root.post("/api/projects", json={"key": "SHOP", "name": "Shop"})).json()["id"]
    await root.post(
        f"/api/projects/{pid}/members", json={"email": "manager@x.vn", "role": "manager"}
    )
    await root.post(f"/api/projects/{pid}/members", json={"email": "viewer@x.vn", "role": "viewer"})
    return root, await login_as("manager@x.vn"), await login_as("viewer@x.vn"), pid


async def test_environment_crud_and_defaults(make_user: MakeUser, login_as: LoginAs) -> None:
    root, manager, viewer, pid = await _project_with_manager(make_user, login_as)
    r = await manager.post(
        f"/api/projects/{pid}/environments",
        json={"name": "UAT", "kind": "uat", "base_url": "https://uat.shop.vn"},
    )
    assert r.status_code == 201
    env = r.json()
    assert env["requires_run_confirmation"] is True  # UAT mặc định cần xác nhận
    dev = (
        await manager.post(
            f"/api/projects/{pid}/environments",
            json={"name": "Dev", "kind": "dev", "base_url": "http://dev.shop.vn"},
        )
    ).json()
    assert dev["requires_run_confirmation"] is False
    assert (
        await manager.post(
            f"/api/projects/{pid}/environments",
            json={"name": "Dev", "kind": "dev", "base_url": "http://x.vn"},
        )
    ).status_code == 409
    assert (
        await viewer.post(
            f"/api/projects/{pid}/environments",
            json={"name": "T", "kind": "test", "base_url": "http://x.vn"},
        )
    ).status_code == 403
    assert len((await viewer.get(f"/api/projects/{pid}/environments")).json()) == 2

    upd = await manager.patch(
        f"/api/environments/{env['id']}",
        json={"base_url": "https://uat2.shop.vn", "allowed_hosts": ["api.shop.vn"]},
    )
    assert upd.status_code == 200 and upd.json()["allowed_hosts"] == ["api.shop.vn"]
    # Chỉ Admin dự án được xóa môi trường.
    assert (await manager.delete(f"/api/environments/{env['id']}")).status_code == 403
    assert (await root.delete(f"/api/environments/{env['id']}")).status_code == 204


async def test_private_network_requires_admin(make_user: MakeUser, login_as: LoginAs) -> None:
    root, manager, _, pid = await _project_with_manager(make_user, login_as)
    body = {
        "name": "Noi bo",
        "kind": "test",
        "base_url": "http://10.0.0.5",
        "allow_private_network": True,
    }
    assert (await manager.post(f"/api/projects/{pid}/environments", json=body)).status_code == 403
    r = await root.post(f"/api/projects/{pid}/environments", json=body)
    assert r.status_code == 201 and r.json()["allow_private_network"] is True
    assert (
        await manager.patch(
            f"/api/environments/{r.json()['id']}", json={"allow_private_network": False}
        )
    ).status_code == 403


async def test_secret_variable_never_exposed_and_encrypted_at_rest(
    make_user: MakeUser, login_as: LoginAs
) -> None:
    _, manager, viewer, pid = await _project_with_manager(make_user, login_as)
    eid = (
        await manager.post(
            f"/api/projects/{pid}/environments",
            json={"name": "Dev", "kind": "dev", "base_url": "https://dev.vn"},
        )
    ).json()["id"]

    r = await manager.post(
        f"/api/environments/{eid}/variables",
        json={"key": "API_TOKEN", "value": SECRET, "is_secret": True},
    )
    assert r.status_code == 201
    assert r.json()["value"] is None and r.json()["has_value"] is True
    assert SECRET not in r.text
    plain = await manager.post(
        f"/api/environments/{eid}/variables", json={"key": "TIMEOUT_MS", "value": "5000"}
    )
    assert plain.json()["value"] == "5000"
    assert (
        await manager.post(
            f"/api/environments/{eid}/variables", json={"key": "API_TOKEN", "value": "x"}
        )
    ).status_code == 409

    listing = await viewer.get(f"/api/environments/{eid}/variables")
    assert listing.status_code == 200 and SECRET not in listing.text

    vid = r.json()["id"]
    # Sửa mô tả không cần nhập lại secret; giá trị cũ giữ nguyên.
    await manager.patch(
        f"/api/environments/{eid}/variables/{vid}", json={"description": "Token API"}
    )
    async with get_sessionmaker()() as db:
        var = await db.get(EnvironmentVariable, uuid.UUID(vid))
        assert var is not None and var.value is None and var.encrypted_value
        assert SECRET.encode() not in var.encrypted_value
        from omnitest_api.config import get_settings
        from omnitest_api.deps import get_cipher

        assert get_cipher(get_settings()).decrypt(var.encrypted_value, f"envvar:{vid}") == SECRET
        audits = list(await db.scalars(select(AuditLog)))
    assert all(SECRET not in str(a.details) for a in audits)
    assert any(a.action == "variable.create" for a in audits)

    assert (
        await viewer.patch(f"/api/environments/{eid}/variables/{vid}", json={"value": "x"})
    ).status_code == 403
    assert (await manager.delete(f"/api/environments/{eid}/variables/{vid}")).status_code == 204


async def test_variable_from_other_environment_is_404(
    make_user: MakeUser, login_as: LoginAs
) -> None:
    _, manager, _, pid = await _project_with_manager(make_user, login_as)
    e1 = (
        await manager.post(
            f"/api/projects/{pid}/environments",
            json={"name": "A", "kind": "dev", "base_url": "https://a.vn"},
        )
    ).json()["id"]
    e2 = (
        await manager.post(
            f"/api/projects/{pid}/environments",
            json={"name": "B", "kind": "dev", "base_url": "https://b.vn"},
        )
    ).json()["id"]
    vid = (
        await manager.post(f"/api/environments/{e1}/variables", json={"key": "K", "value": "v"})
    ).json()["id"]
    assert (
        await manager.patch(f"/api/environments/{e2}/variables/{vid}", json={"value": "y"})
    ).status_code == 404
