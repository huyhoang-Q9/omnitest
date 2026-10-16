"""Conftest gốc do sandbox OmniTest thêm vào: trình duyệt của pytest-playwright đi qua proxy kiểm soát mạng."""

import os
from typing import Any

import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict[str, Any]) -> dict[str, Any]:
    proxy = os.environ.get("OMNITEST_PROXY")
    if not proxy:
        return browser_type_launch_args
    return {**browser_type_launch_args, "proxy": {"server": proxy, "bypass": "<-loopback>"}}
