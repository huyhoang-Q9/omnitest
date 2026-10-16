"""Adapter Appium (Desktop/Mobile).

Phần 1 luôn chạy: không có Appium server, không có bước, capability bị cấm đều báo đúng, không bao giờ báo đạt.
Phần 2 chạy với Appium server THẬT dùng driver "fake" chính thức của Appium (ứng dụng mô phỏng từ XML), để kiểm
chứng giao thức W3C WebDriver của adapter. Không thay thế kiểm thử trên thiết bị/máy macOS/Windows thật.
Bật phần 2: đặt OMNITEST_APPIUM_BIN (đường dẫn lệnh appium) và APPIUM_HOME có driver fake.
"""

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from omnitest_adapters.appium.adapter import AppiumAdapter
from omnitest_adapters.core.base import ExecutionContext
from omnitest_adapters.core.definitions import AppTestDefinition
from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.core.results import Outcome
from omnitest_adapters.core.templating import Variables
from pydantic import ValidationError

FAKE_APP = str(Path(__file__).parent / "fixtures" / "fake_app.xml")
SECRET = "Mat-khau-bi-mat"
ADAPTER = AppiumAdapter("mobile-appium", "Mobile", ("mobile_android", "mobile_ios"))


def ctx(base: str, private: bool = True, **settings: Any) -> ExecutionContext:
    async def no() -> bool:
        return False

    return ExecutionContext(
        base_url=base,
        variables=Variables({"USER": "demo", "PASS": SECRET, "APP": FAKE_APP}, {"PASS"}),
        policy=NetworkPolicy.from_environment(base, (), private),
        deadline=time.monotonic() + 60,
        is_cancelled=no,
        settings=settings,
    )


def app(steps: list[dict[str, Any]], **kw: Any) -> AppTestDefinition:
    return AppTestDefinition.model_validate({"kind": "mobile_android", "steps": steps, **kw})


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_no_steps_is_blocked() -> None:
    r = await ADAPTER.execute(ctx("http://127.0.0.1:4723"), app([], notes="Làm tay"))
    assert r.status == Outcome.BLOCKED and r.error_type == "no_steps"


async def test_unreachable_server_is_blocked_not_passed() -> None:
    port = _free_port()
    r = await ADAPTER.execute(
        ctx(f"http://127.0.0.1:{port}"), app([{"name": "Chụp", "action": "screenshot"}])
    )
    assert r.status == Outcome.BLOCKED and r.error_type == "appium_unavailable"


async def test_server_on_private_network_needs_opt_in() -> None:
    r = await ADAPTER.execute(
        ctx("http://127.0.0.1:4723", private=False), app([{"name": "Chụp", "action": "screenshot"}])
    )
    assert r.status == Outcome.BLOCKED and r.error_type == "blocked_target"


@pytest.mark.parametrize(
    "caps",
    [
        {"chromedriverExecutable": "/usr/local/bin/chromedriver"},
        {"appium:relaxedSecurityEnabled": True},
        {"app": "https://evil.example/app.apk"},
    ],
)
def test_dangerous_capabilities_rejected(caps: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        app([{"name": "a", "action": "back"}], capabilities=caps)


def test_step_validation() -> None:
    with pytest.raises(ValidationError, match="cần locator"):
        app([{"name": "a", "action": "tap"}])
    with pytest.raises(ValidationError, match="cần value"):
        app([{"name": "a", "action": "type", "locator": {"value": "x"}}])
    # Test cũ chỉ có mô tả vẫn hợp lệ.
    assert AppTestDefinition.model_validate({"kind": "desktop_macos", "notes": "x"}).steps == []


# ---------------------------------------------------------------- Appium server thật + driver fake

APPIUM_BIN = os.environ.get("OMNITEST_APPIUM_BIN")


@pytest.fixture(scope="module")
def appium_url() -> Iterator[str]:
    if not APPIUM_BIN or not Path(APPIUM_BIN).exists():
        pytest.skip("Cần OMNITEST_APPIUM_BIN và APPIUM_HOME có driver fake để chạy với Appium thật")
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 - lệnh do người chạy test cấu hình
        [APPIUM_BIN, "--address", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{url}/status", trust_env=False, timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.fail("Appium server không khởi động")
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


FAKE = {"appium_platform_override": {"platformName": "Fake", "automationName": "Fake"}}
CAPS = {"app": "{{APP}}", "deviceName": "Fake"}


async def test_real_appium_flow_passes_and_masks_secret(appium_url: str) -> None:
    r = await ADAPTER.execute(
        ctx(appium_url, **FAKE),
        app(
            [
                {
                    "name": "Nhập",
                    "action": "type",
                    "locator": {"strategy": "id", "value": "username"},
                    "value": "{{PASS}}",
                },
                {"name": "Thấy nút", "action": "expect_visible", "locator": {"value": "login"}},
                {"name": "Bấm", "action": "tap", "locator": {"value": "login"}},
                {
                    "name": "Tìm",
                    "action": "type",
                    "locator": {"value": "search"},
                    "value": "Xin chào kho hàng",
                },
                {
                    "name": "Lời chào",
                    "action": "expect_text",
                    "locator": {"strategy": "xpath", "value": "//MockInputField[@id='search']"},
                    "value": "kho hàng",
                },
                {"name": "Ẩn", "action": "expect_hidden", "locator": {"value": "hidden"}},
                {"name": "Chụp", "action": "screenshot"},
            ],
            capabilities=CAPS,
        ),
    )
    assert r.status == Outcome.PASSED, [(s.name, s.status, s.error) for s in r.steps]
    assert len(r.steps) == 7 and r.steps[6].artifacts[0].data[:4] == b"\x89PNG"
    assert SECRET not in repr([s.log for s in r.steps]) and "***" in r.steps[0].log[0]


async def test_real_appium_missing_element_fails_with_screenshot(appium_url: str) -> None:
    r = await ADAPTER.execute(
        ctx(appium_url, **FAKE),
        app(
            [
                {
                    "name": "Không có",
                    "action": "tap",
                    "locator": {"value": "khong-ton-tai"},
                    "timeout_ms": 600,
                },
                {"name": "Sau", "action": "back"},
            ],
            capabilities=CAPS,
        ),
    )
    assert r.status == Outcome.FAILED and r.error_type == "not_found"
    assert r.steps[0].artifacts and r.steps[1].status == Outcome.SKIPPED


async def test_real_appium_wrong_text_fails(appium_url: str) -> None:
    r = await ADAPTER.execute(
        ctx(appium_url, **FAKE),
        app(
            [
                {
                    "name": "Sai",
                    "action": "expect_text",
                    "locator": {"value": "search"},
                    "value": "tạm biệt",
                    "timeout_ms": 500,
                }
            ],
            capabilities=CAPS,
        ),
    )
    assert r.status == Outcome.FAILED and r.error_type == "assertion"


async def test_real_appium_missing_driver_is_blocked(appium_url: str) -> None:
    # Android cần driver UiAutomator2 và thiết bị; server này không có nên phải báo Bị chặn.
    r = await ADAPTER.execute(ctx(appium_url), app([{"name": "Chụp", "action": "screenshot"}]))
    assert r.status == Outcome.BLOCKED and r.error_type == "appium_session"
