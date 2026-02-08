"""Shared fixtures for API tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app


@pytest.fixture
async def app(tmp_path):
    db_path = tmp_path / "test.db"
    test_app = create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key="test-key",
    )
    yield test_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key"}
