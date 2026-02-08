"""Tests for camera node registration endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from waggle.auth import create_admin_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app

ADMIN_KEY = "test-admin-key-secret"
API_KEY = "test-api-key"


@pytest.fixture
async def app(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    application = create_app(
        db_url=db_url,
        api_key=API_KEY,
    )
    # Manually init DB since ASGITransport does not trigger ASGI lifespan
    engine = create_engine_from_url(db_url)
    await init_db(engine)
    application.state.engine = engine

    # Mount admin router (Task 5.1 will wire it permanently via create_app)
    from waggle.routers import admin

    verify_admin = create_admin_key_dependency(ADMIN_KEY)
    application.include_router(admin.create_router(verify_admin), prefix="/api")

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_hive(client):
    """Create a test hive for camera node tests."""
    resp = await client.post(
        "/api/hives",
        json={"id": 1, "name": "Test Hive"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_register_camera_node(client):
    await _seed_hive(client)
    resp = await client.post(
        "/api/admin/camera-nodes",
        json={
            "device_id": "cam-hive01-a",
            "hive_id": 1,
            "api_key": "a" * 32,  # min 32 chars
        },
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["device_id"] == "cam-hive01-a"
    assert data["hive_id"] == 1
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_device(client):
    await _seed_hive(client)
    body = {"device_id": "cam-dup", "hive_id": 1, "api_key": "a" * 32}
    headers = {"X-Admin-Key": ADMIN_KEY}
    resp1 = await client.post("/api/admin/camera-nodes", json=body, headers=headers)
    assert resp1.status_code == 201
    resp2 = await client.post("/api/admin/camera-nodes", json=body, headers=headers)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_hive(client):
    resp = await client.post(
        "/api/admin/camera-nodes",
        json={"device_id": "cam-99", "hive_id": 99, "api_key": "a" * 32},
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_register_without_admin_key(client):
    await _seed_hive(client)
    resp = await client.post(
        "/api/admin/camera-nodes",
        json={"device_id": "cam-noauth", "hive_id": 1, "api_key": "a" * 32},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_with_regular_api_key(client):
    await _seed_hive(client)
    resp = await client.post(
        "/api/admin/camera-nodes",
        json={"device_id": "cam-apikey", "hive_id": 1, "api_key": "a" * 32},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 401
