"""Registry mặc định: đăng ký toàn bộ adapter đã biết."""

from functools import lru_cache

from omnitest_adapters import (
    api_httpx,
    desktop_macos,
    desktop_windows,
    mobile_appium,
    web_playwright,
)
from omnitest_adapters.core.base import AdapterRegistry


@lru_cache
def default_registry() -> AdapterRegistry:
    reg = AdapterRegistry()
    for mod in (api_httpx, web_playwright, desktop_macos, desktop_windows, mobile_appium):
        reg.register(mod.adapter)
    return reg
