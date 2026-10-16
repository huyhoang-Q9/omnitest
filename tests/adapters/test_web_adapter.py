import time
from typing import Any

import pytest
from omnitest_adapters.core.base import ExecutionContext
from omnitest_adapters.core.definitions import WebTestDefinition
from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.core.results import Outcome
from omnitest_adapters.core.templating import Variables
from omnitest_adapters.web_playwright.adapter import WebPlaywrightAdapter

from tests.adapters.conftest import chromium_available

pytestmark = pytest.mark.skipif(
    not chromium_available(), reason="Cần OMNITEST_CHROMIUM_EXECUTABLE trỏ tới Chromium"
)
SECRET = "Demo@123"


def ctx(base: str, private: bool = True) -> ExecutionContext:
    async def no() -> bool:
        return False

    return ExecutionContext(
        base_url=base,
        variables=Variables({"USER": "demo", "PASS": SECRET}, {"PASS"}),
        policy=NetworkPolicy.from_environment(base, (), private),
        deadline=time.monotonic() + 60,
        is_cancelled=no,
    )


def web(steps: list[dict[str, Any]], **kw: Any) -> WebTestDefinition:
    return WebTestDefinition.model_validate({"kind": "web", "steps": steps, **kw})


LOGIN_STEPS = [
    {"name": "Mở trang", "action": "goto", "value": "/login"},
    {"name": "Nhập tên", "action": "fill", "selector": "label=Tên đăng nhập", "value": "{{USER}}"},
    {"name": "Nhập mật khẩu", "action": "fill", "selector": "label=Mật khẩu", "value": "{{PASS}}"},
    {"name": "Bấm đăng nhập", "action": "click", "selector": 'role=button[name="Đăng nhập"]'},
]


async def test_login_and_crud(demo_url: str) -> None:
    d = web(
        [
            *LOGIN_STEPS,
            {"name": "Vào danh sách", "action": "expect_url", "value": "/items"},
            {
                "name": "Nhập tên hàng",
                "action": "fill",
                "selector": "label=Tên hàng",
                "value": "Thước kẻ",
            },
            {"name": "Thêm", "action": "click", "selector": 'role=button[name="Thêm hàng"]'},
            {
                "name": "Thấy hàng mới",
                "action": "expect_text",
                "selector": "table",
                "value": "Thước kẻ",
            },
            {"name": "Xóa", "action": "click", "selector": 'role=button[name="Xóa Thước kẻ"]'},
            {"name": "Đã xóa", "action": "expect_hidden", "selector": "text=Thước kẻ"},
            {"name": "Chụp màn hình", "action": "screenshot"},
        ],
        trace="off",
    )
    r = await WebPlaywrightAdapter().execute(ctx(demo_url), d)
    assert r.status == Outcome.PASSED, (r.error, [(s.name, s.status, s.error) for s in r.steps])
    assert r.steps[-1].artifacts and r.steps[-1].artifacts[0].content_type == "image/png"
    assert SECRET not in repr([s.log for s in r.steps])


async def test_form_validation_messages(demo_url: str) -> None:
    d = web(
        [
            {"name": "Mở", "action": "goto", "value": "/register"},
            {"name": "Tuổi sai", "action": "fill", "selector": "label=Tuổi", "value": "10"},
            {"name": "Gửi", "action": "click", "selector": 'role=button[name="Đăng ký"]'},
            {
                "name": "Lỗi họ tên",
                "action": "expect_text",
                "selector": "#full_name-error",
                "value": "Vui lòng nhập họ tên",
            },
            {
                "name": "Lỗi tuổi",
                "action": "expect_text",
                "selector": "#age-error",
                "value": "Tuổi phải từ 18 đến 100",
            },
        ],
        trace="off",
    )
    r = await WebPlaywrightAdapter().execute(ctx(demo_url), d)
    assert r.status == Outcome.PASSED, r.error


async def test_failure_produces_screenshot_and_trace(demo_url: str) -> None:
    d = web(
        [
            {"name": "Mở", "action": "goto", "value": "/login"},
            {
                "name": "Chờ chữ không có",
                "action": "expect_text",
                "selector": "h1",
                "value": "Không tồn tại",
                "timeout_ms": 800,
            },
            {"name": "Không chạy", "action": "click", "selector": "button"},
        ]
    )
    r = await WebPlaywrightAdapter().execute(ctx(demo_url), d)
    assert r.status == Outcome.FAILED
    assert r.steps[1].status == Outcome.FAILED and r.steps[2].status == Outcome.SKIPPED
    assert any(a.kind == "screenshot" for a in r.steps[1].artifacts)
    assert any(a.kind == "trace" for a in r.artifacts)


async def test_navigation_outside_allowlist_blocked(demo_url: str) -> None:
    r = await WebPlaywrightAdapter().execute(
        ctx(demo_url),
        web(
            [{"name": "Ra ngoài", "action": "goto", "value": "http://169.254.169.254/"}],
            trace="off",
        ),
    )
    assert r.status == Outcome.BLOCKED


async def test_private_network_blocked_for_browser(demo_url: str) -> None:
    r = await WebPlaywrightAdapter().execute(
        ctx(demo_url, private=False), web(LOGIN_STEPS[:1], trace="off")
    )
    assert r.status == Outcome.BLOCKED
