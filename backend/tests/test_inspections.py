"""Tests for inspections CRUD endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.auth import create_api_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import Hive
from waggle.routers import inspections
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
    application.include_router(inspections.create_router(verify_key), prefix="/api")

    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test Hive", created_at=utc_now())
        session.add(hive)
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


HEADERS = {"X-API-Key": API_KEY}


async def test_create_inspection(client):
    resp = await client.post(
        "/api/inspections",
        json={
            "hive_id": 1,
            "inspected_at": "2026-02-08T12:00:00.000Z",
            "queen_seen": True,
            "brood_pattern": "good",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["hive_id"] == 1
    assert data["queen_seen"] is True
    assert data["source"] == "local"
    assert "uuid" in data


async def test_create_inspection_idempotent(client):
    body = {
        "uuid": "test-uuid-123",
        "hive_id": 1,
        "inspected_at": "2026-02-08T12:00:00.000Z",
    }
    resp1 = await client.post("/api/inspections", json=body, headers=HEADERS)
    assert resp1.status_code == 201
    resp2 = await client.post("/api/inspections", json=body, headers=HEADERS)
    assert resp2.status_code == 200  # Idempotent
    assert resp2.json()["uuid"] == "test-uuid-123"


async def test_create_inspection_invalid_hive(client):
    # Use a valid range but non-existent hive
    resp = await client.post(
        "/api/inspections",
        json={"hive_id": 99, "inspected_at": "2026-02-08T12:00:00.000Z"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


async def test_update_inspection(client):
    # Create first
    resp = await client.post(
        "/api/inspections",
        json={
            "uuid": "update-me",
            "hive_id": 1,
            "inspected_at": "2026-02-08T12:00:00.000Z",
            "queen_seen": False,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201

    # Update
    resp = await client.put(
        "/api/inspections/update-me",
        json={
            "hive_id": 1,
            "inspected_at": "2026-02-08T14:00:00.000Z",
            "queen_seen": True,
            "brood_pattern": "patchy",
            "notes": "Treated with oxalic acid",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queen_seen"] is True
    assert data["brood_pattern"] == "patchy"
    assert data["notes"] == "Treated with oxalic acid"
    assert data["source"] == "local"


async def test_update_inspection_not_found(client):
    resp = await client.put(
        "/api/inspections/nonexistent",
        json={"hive_id": 1, "inspected_at": "2026-02-08T12:00:00.000Z"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


async def test_list_inspections(client):
    # Create two inspections
    await client.post(
        "/api/inspections",
        json={"hive_id": 1, "inspected_at": "2026-02-07T12:00:00.000Z"},
        headers=HEADERS,
    )
    await client.post(
        "/api/inspections",
        json={"hive_id": 1, "inspected_at": "2026-02-08T12:00:00.000Z"},
        headers=HEADERS,
    )
    resp = await client.get(
        "/api/hives/1/inspections",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Default order is desc
    assert data["items"][0]["inspected_at"] >= data["items"][1]["inspected_at"]


async def test_list_inspections_invalid_hive(client):
    resp = await client.get("/api/hives/999/inspections", headers=HEADERS)
    assert resp.status_code == 404


async def test_inspections_no_auth(client):
    resp = await client.post(
        "/api/inspections",
        json={"hive_id": 1, "inspected_at": "2026-02-08T12:00:00.000Z"},
    )
    assert resp.status_code == 401
