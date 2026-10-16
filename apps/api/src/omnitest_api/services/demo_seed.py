"""Tạo dự án demo trỏ tới ứng dụng demo-target "Kho hàng mini".

Đi qua đúng API của hệ thống (kiểm tra dữ liệu, mã hóa secret, ghi audit) bằng một phiên đăng nhập
ngắn hạn của chủ dự án, phiên bị xóa ngay sau khi tạo xong. Không ghi đè: nếu mã dự án đã tồn tại thì dừng.

Tài khoản demo / Demo@123 là tài khoản công khai của ứng dụng demo, không phải bí mật thật.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, func, select

from omnitest_api.config import get_settings
from omnitest_api.db import get_sessionmaker
from omnitest_api.models import Project, User, UserSession
from omnitest_api.security.sessions import hash_token, new_session_token

DEMO_KEY = "DEMO"
DEMO_USER = "demo"
DEMO_PASSWORD = "Demo@123"  # noqa: S105 - tài khoản công khai của ứng dụng demo

STATUS_200 = {"type": "status", "equals": 200}
LOGIN_API_STEP: dict[str, Any] = {
    "name": "Đăng nhập API lấy token",
    "method": "POST",
    "url": "/api/login",
    "body_type": "json",
    "body": {"username": "{{DEMO_USER}}", "password": "{{DEMO_PASSWORD}}"},
    "assertions": [STATUS_200, {"type": "json_path", "path": "$.token", "op": "exists"}],
    "extract": [{"var": "TOKEN", "source": "json_path", "expression": "$.token"}],
}
BEARER = {"type": "bearer", "token": "{{TOKEN}}"}
WEB_LOGIN_STEPS: list[dict[str, Any]] = [
    {"name": "Mở trang đăng nhập", "action": "goto", "value": "/login"},
    {
        "name": "Nhập tên",
        "action": "fill",
        "selector": "label=Tên đăng nhập",
        "value": "{{DEMO_USER}}",
    },
    {
        "name": "Nhập mật khẩu",
        "action": "fill",
        "selector": "label=Mật khẩu",
        "value": "{{DEMO_PASSWORD}}",
    },
    {"name": "Bấm đăng nhập", "action": "click", "selector": 'role=button[name="Đăng nhập"]'},
]

CASES: list[dict[str, Any]] = [
    {
        "title": "API health trả về ok",
        "priority": "high",
        "tags": ["smoke", "api"],
        "expected_result": "Mã 200 và status = ok",
        "definition": {
            "kind": "api",
            "steps": [
                {
                    "name": "Gọi /api/health",
                    "url": "/api/health",
                    "assertions": [
                        STATUS_200,
                        {"type": "json_path", "path": "$.status", "value": "ok"},
                        {"type": "response_time", "max_ms": 2000},
                    ],
                }
            ],
        },
    },
    {
        "title": "API đăng nhập sai mật khẩu bị từ chối",
        "priority": "high",
        "tags": ["smoke", "api", "auth"],
        "expected_result": "Mã 401",
        "side_effect": False,
        "definition": {
            "kind": "api",
            "steps": [
                {
                    "name": "Đăng nhập sai",
                    "method": "POST",
                    "url": "/api/login",
                    "body_type": "json",
                    "body": {"username": "{{DEMO_USER}}", "password": "sai-mat-khau"},
                    "assertions": [{"type": "status", "equals": 401}],
                }
            ],
        },
    },
    {
        "title": "API đăng nhập và xem danh sách hàng",
        "priority": "high",
        "tags": ["smoke", "api"],
        "side_effect": False,
        "definition": {
            "kind": "api",
            "steps": [
                LOGIN_API_STEP,
                {
                    "name": "Lấy danh sách hàng",
                    "url": "/api/items",
                    "auth": BEARER,
                    "assertions": [
                        STATUS_200,
                        {
                            "type": "json_schema",
                            "schema": {
                                "type": "object",
                                "required": ["items", "total"],
                                "properties": {
                                    "items": {"type": "array"},
                                    "total": {"type": "integer"},
                                },
                            },
                        },
                    ],
                },
            ],
        },
    },
    {
        "title": "API thêm, sửa, xóa mặt hàng",
        "priority": "medium",
        "tags": ["api", "crud"],
        "definition": {
            "kind": "api",
            "steps": [
                LOGIN_API_STEP,
                {
                    "name": "Thêm hàng",
                    "method": "POST",
                    "url": "/api/items",
                    "auth": BEARER,
                    "body_type": "json",
                    "body": {"name": "Thước kẻ", "quantity": 10},
                    "assertions": [{"type": "status", "equals": 201}],
                    "extract": [{"var": "ITEM_ID", "source": "json_path", "expression": "$.id"}],
                },
                {
                    "name": "Sửa số lượng",
                    "method": "PUT",
                    "url": "/api/items/{{ITEM_ID}}",
                    "auth": BEARER,
                    "body_type": "json",
                    "body": {"name": "Thước kẻ", "quantity": 25},
                    "assertions": [
                        STATUS_200,
                        {"type": "json_path", "path": "$.quantity", "value": 25},
                    ],
                },
                {
                    "name": "Xóa hàng",
                    "method": "DELETE",
                    "url": "/api/items/{{ITEM_ID}}",
                    "auth": BEARER,
                    "assertions": [{"type": "status", "equals": 204}],
                },
                {
                    "name": "Kiểm tra đã xóa",
                    "url": "/api/items/{{ITEM_ID}}",
                    "auth": BEARER,
                    "assertions": [{"type": "status", "equals": 404}],
                },
            ],
        },
    },
    {
        "title": "Web đăng nhập thành công",
        "priority": "high",
        "tags": ["smoke", "web", "auth"],
        "definition": {
            "kind": "web",
            "trace": "on_failure",
            "steps": [
                *WEB_LOGIN_STEPS,
                {"name": "Chuyển tới danh sách hàng", "action": "expect_url", "value": "/items"},
                {
                    "name": "Hiện lời chào",
                    "action": "expect_text",
                    "selector": "text=Xin chào",
                    "value": "demo",
                },
                {"name": "Chụp màn hình", "action": "screenshot"},
            ],
        },
    },
    {
        "title": "Web đăng nhập sai hiện thông báo lỗi",
        "priority": "medium",
        "tags": ["web", "auth"],
        "definition": {
            "kind": "web",
            "steps": [
                {"name": "Mở trang đăng nhập", "action": "goto", "value": "/login"},
                {
                    "name": "Nhập tên",
                    "action": "fill",
                    "selector": "label=Tên đăng nhập",
                    "value": "demo",
                },
                {
                    "name": "Nhập mật khẩu sai",
                    "action": "fill",
                    "selector": "label=Mật khẩu",
                    "value": "sai",
                },
                {
                    "name": "Bấm đăng nhập",
                    "action": "click",
                    "selector": 'role=button[name="Đăng nhập"]',
                },
                {
                    "name": "Thông báo lỗi",
                    "action": "expect_text",
                    "selector": "role=alert",
                    "value": "Sai tên đăng nhập",
                },
            ],
        },
    },
    {
        "title": "Web form đăng ký báo lỗi kiểm tra dữ liệu",
        "priority": "medium",
        "tags": ["web", "validation"],
        "definition": {
            "kind": "web",
            "steps": [
                {"name": "Mở trang đăng ký", "action": "goto", "value": "/register"},
                {
                    "name": "Email sai",
                    "action": "fill",
                    "selector": "label=Email",
                    "value": "khong-hop-le",
                },
                {"name": "Tuổi nhỏ", "action": "fill", "selector": "label=Tuổi", "value": "12"},
                {"name": "Gửi", "action": "click", "selector": 'role=button[name="Đăng ký"]'},
                {
                    "name": "Lỗi họ tên",
                    "action": "expect_text",
                    "selector": "#full_name-error",
                    "value": "Vui lòng nhập họ tên",
                },
                {
                    "name": "Lỗi email",
                    "action": "expect_text",
                    "selector": "#email-error",
                    "value": "Email không hợp lệ",
                },
                {
                    "name": "Lỗi tuổi",
                    "action": "expect_text",
                    "selector": "#age-error",
                    "value": "Tuổi phải từ 18 đến 100",
                },
                {"name": "Lỗi mật khẩu", "action": "expect_visible", "selector": "#password-error"},
            ],
        },
    },
    {
        "title": "Web thêm và xóa mặt hàng",
        "priority": "medium",
        "tags": ["web", "crud"],
        "side_effect": True,
        "definition": {
            "kind": "web",
            "trace": "on_failure",
            "steps": [
                *WEB_LOGIN_STEPS,
                {
                    "name": "Nhập tên hàng",
                    "action": "fill",
                    "selector": "label=Tên hàng",
                    "value": "Kẹp giấy",
                },
                {
                    "name": "Nhập số lượng",
                    "action": "fill",
                    "selector": "label=Số lượng",
                    "value": "7",
                },
                {"name": "Thêm", "action": "click", "selector": 'role=button[name="Thêm hàng"]'},
                {
                    "name": "Hàng mới xuất hiện",
                    "action": "expect_visible",
                    "selector": "text=Kẹp giấy",
                },
                {"name": "Xóa", "action": "click", "selector": 'role=button[name="Xóa Kẹp giấy"]'},
                {
                    "name": "Hàng đã biến mất",
                    "action": "expect_hidden",
                    "selector": "text=Kẹp giấy",
                },
            ],
        },
    },
]


class SeedError(Exception):
    pass


async def seed_demo(owner_email: str, base_url: str) -> dict[str, Any]:
    from omnitest_api.main import create_app

    settings = get_settings()
    async with get_sessionmaker()() as db:
        owner = await db.scalar(select(User).where(func.lower(User.email) == owner_email.lower()))
        if owner is None or not owner.is_active or not owner.is_system_admin:
            raise SeedError(f"{owner_email} phải là quản trị hệ thống đang hoạt động")
        if await db.scalar(select(Project.id).where(Project.key == DEMO_KEY)):
            raise SeedError(
                f"Dự án {DEMO_KEY} đã tồn tại, không ghi đè. Hãy xóa hoặc đổi mã trước."
            )
        token = new_session_token()
        session = UserSession(
            id=uuid.uuid4(),
            user_id=owner.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            user_agent="omnitest-api seed-demo",
        )
        db.add(session)
        await db.commit()

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()),
            base_url="http://seed.local",
            headers={"X-OmniTest-CSRF": "1"},
            cookies={settings.session_cookie_name: token},
        ) as c:

            async def post(url: str, body: dict[str, Any]) -> dict[str, Any]:
                r = await c.post(url, json=body)
                if r.status_code >= 400:
                    raise SeedError(f"{url}: {r.status_code} {r.text[:500]}")
                return dict(r.json())

            project = await post(
                "/api/projects",
                {
                    "key": DEMO_KEY,
                    "name": "Kho hàng mini (demo)",
                    "description": "Dự án mẫu kiểm thử ứng dụng demo-target đi kèm OmniTest.",
                },
            )
            pid = project["id"]
            env = await post(
                f"/api/projects/{pid}/environments",
                {
                    "name": "Demo local",
                    "kind": "dev",
                    "base_url": base_url,
                    "description": "Ứng dụng demo-target chạy cùng OmniTest",
                    "allow_private_network": True,
                },
            )
            await post(
                f"/api/environments/{env['id']}/variables",
                {"key": "DEMO_USER", "value": DEMO_USER, "description": "Tài khoản demo"},
            )
            await post(
                f"/api/environments/{env['id']}/variables",
                {
                    "key": "DEMO_PASSWORD",
                    "value": DEMO_PASSWORD,
                    "is_secret": True,
                    "description": "Mật khẩu tài khoản demo",
                },
            )
            ids: list[str] = []
            smoke: list[str] = []
            for case in CASES:
                body = {"status": "ready", "test_type": case["definition"]["kind"], **case}
                tc = await post(f"/api/projects/{pid}/test-cases", body)
                ids.append(tc["id"])
                if "smoke" in case["tags"]:
                    smoke.append(tc["id"])
            for name, desc, members in (
                ("Smoke", "Kiểm tra nhanh các luồng chính", smoke),
                ("Hồi quy đầy đủ", "Toàn bộ test mẫu, gồm cả test thay đổi dữ liệu", ids),
            ):
                suite = await post(
                    f"/api/projects/{pid}/suites", {"name": name, "description": desc}
                )
                r = await c.put(f"/api/suites/{suite['id']}/items", json={"test_case_ids": members})
                if r.status_code >= 400:
                    raise SeedError(f"suite items: {r.status_code} {r.text[:500]}")
            return {
                "project_id": pid,
                "environment_id": env["id"],
                "test_cases": len(ids),
                "suites": 2,
            }
    finally:
        async with get_sessionmaker()() as db:
            await db.execute(delete(UserSession).where(UserSession.id == session.id))
            await db.commit()
