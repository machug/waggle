"""Tests for sync status endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.auth import create_api_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import Hive, SyncState
from waggle.routers import sync
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key"


@pytest.fixture
async def app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)

    application = create_app(db_url=f"sqlite+aiosqlite:///{db_path}", api_key=API_KEY)
    application.state.engine = engine

    verify_key = create_api_key_dependency(API_KEY)
    application.include_router(sync.create_router(verify_key), prefix="/api")

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


HEADERS = {"X-API-Key": API_KEY}


async def test_sync_status_empty(client):
    resp = await client.get("/api/sync/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_push_at"] is None
    assert data["last_pull_inspections_at"] is None
    assert data["last_pull_alerts_at"] is None
    assert data["pending_rows"] == 0
    assert data["pending_files"] == 0


async def test_sync_status_with_data(client, app):
    async with AsyncSession(app.state.engine) as session:
        # Add sync state entry
        session.add(SyncState(key="last_push_at", value="2026-02-08T12:00:00.000Z"))
        # Add a hive (row_synced defaults to 0)
        session.add(Hive(id=1, name="Test", created_at=utc_now()))
        await session.commit()

    resp = await client.get("/api/sync/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_push_at"] == "2026-02-08T12:00:00.000Z"
    assert data["pending_rows"] >= 1  # At least the hive


async def test_sync_status_no_auth(client):
    resp = await client.get("/api/sync/status")
    assert resp.status_code == 401
