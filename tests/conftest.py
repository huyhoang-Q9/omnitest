"""Fixture dùng chung. Test chạy trên PostgreSQL thật (DB riêng omnitest_test), không mock DB."""

import asyncio
import base64
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

os.environ.setdefault(
    "OMNITEST_TEST_DATABASE_URL",
    "postgresql+asyncpg://omnitest:omnitest@127.0.0.1:5432/omnitest_test",
)
os.environ["OMNITEST_DATABASE_URL"] = os.environ["OMNITEST_TEST_DATABASE_URL"]
os.environ["OMNITEST_ENV"] = "test"
os.environ["OMNITEST_COOKIE_SECURE"] = "false"
os.environ["OMNITEST_QUEUE_BACKEND"] = "none"
os.environ["OMNITEST_ARTIFACTS_DIR"] = tempfile.mkdtemp(prefix="omnitest-artifacts-")
os.environ["OMNITEST_MASTER_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()

import httpx
import pytest
import uvicorn
from omnitest_demo_target.app import app as demo_app
from sqlalchemy import text

from omnitest_api.db import get_engine, get_sessionmaker
from omnitest_api.main import create_app
from omnitest_api.models import Base, User
from omnitest_api.security.passwords import hash_password

API_DIR = Path(__file__).resolve().parents[1] / "apps" / "api"
PASSWORD = "Matkhau-Test-2026"


@pytest.fixture(scope="session")
async def migrated_db() -> AsyncIterator[None]:
    """Đưa DB test về trạng thái rỗng rồi chạy migration thật (đồng thời kiểm tra migration)."""
    async with get_engine().begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        check=True,
        env=os.environ.copy(),
    )
    yield
    await get_engine().dispose()


@pytest.fixture
async def clean_db(migrated_db: None) -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-OmniTest-CSRF": "1"}
    ) as c:
        yield c


MakeUser = Callable[..., Awaitable[User]]


@pytest.fixture
def make_user() -> MakeUser:
    async def _make(email: str, *, admin: bool = False, active: bool = True) -> User:
        async with get_sessionmaker()() as db:
            u = User(
                email=email,
                full_name=email.split("@")[0],
                password_hash=hash_password(PASSWORD),
                is_system_admin=admin,
                is_active=active,
            )
            db.add(u)
            await db.commit()
            return u

    return _make


LoginAs = Callable[[str], Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def login_as() -> AsyncIterator[LoginAs]:
    """Mỗi người dùng một client riêng (cookie riêng)."""
    clients: list[httpx.AsyncClient] = []

    async def _login(email: str) -> httpx.AsyncClient:
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()),
            base_url="http://test",
            headers={"X-OmniTest-CSRF": "1"},
        )
        clients.append(c)
        r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return c

    yield _login
    for c in clients:
        await c.aclose()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def demo_url() -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(demo_app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/api/health", trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield url
    server.should_exit = True
    thread.join(timeout=5)
