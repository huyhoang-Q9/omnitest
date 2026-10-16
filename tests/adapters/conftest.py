"""Adapter test chạy với ứng dụng demo-target thật (uvicorn trên cổng ngẫu nhiên), không mock HTTP."""

import os

import httpx
import pytest


@pytest.fixture(autouse=True)
def _reset(demo_url: str) -> None:
    httpx.post(f"{demo_url}/api/reset", trust_env=False)


def chromium_available() -> bool:
    exe = os.environ.get("OMNITEST_CHROMIUM_EXECUTABLE")
    return bool(exe and os.path.exists(exe))
