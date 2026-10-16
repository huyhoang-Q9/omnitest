from typing import Any

import httpx

API_HEALTH: dict[str, Any] = {
    "kind": "api",
    "steps": [
        {"name": "Health", "url": "/api/health", "assertions": [{"type": "status", "equals": 200}]}
    ],
}
API_LOGIN_FAIL: dict[str, Any] = {
    "kind": "api",
    "steps": [
        {
            "name": "Sai mật khẩu",
            "method": "POST",
            "url": "/api/login",
            "body_type": "json",
            "body": {"username": "demo", "password": "{{DEMO_PASSWORD}}"},
            "assertions": [{"type": "status", "equals": 200}],
        }
    ],
}
WEB_LOGIN: dict[str, Any] = {
    "kind": "web",
    "trace": "off",
    "steps": [
        {"name": "Mở", "action": "goto", "value": "/login"},
        {"name": "Tên", "action": "fill", "selector": "label=Tên đăng nhập", "value": "demo"},
        {
            "name": "Mật khẩu",
            "action": "fill",
            "selector": "label=Mật khẩu",
            "value": "{{DEMO_PASSWORD}}",
        },
        {"name": "Đăng nhập", "action": "click", "selector": 'role=button[name="Đăng nhập"]'},
        {"name": "Vào trang hàng", "action": "expect_url", "value": "/items"},
    ],
}


def case_body(title: str, definition: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"title": title, "test_type": definition["kind"], "definition": definition, **kw}


async def setup_project(
    root: httpx.AsyncClient, base_url: str, *, private: bool = True, key: str = "DEMO"
) -> tuple[str, str]:
    pid = (await root.post("/api/projects", json={"key": key, "name": "Demo"})).json()["id"]
    env = await root.post(
        f"/api/projects/{pid}/environments",
        json={"name": "Dev", "kind": "dev", "base_url": base_url, "allow_private_network": private},
    )
    assert env.status_code == 201, env.text
    eid = env.json()["id"]
    r = await root.post(
        f"/api/environments/{eid}/variables",
        json={"key": "DEMO_PASSWORD", "value": "Demo@123", "is_secret": True},
    )
    assert r.status_code == 201
    return pid, eid
