"""Tests for readings endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import SensorReading


@pytest.fixture
async def app(tmp_path):
    """Override the conftest app fixture to properly initialise the DB engine.

    ASGITransport does not trigger ASGI lifespan events, so we create
    the engine manually and attach it to app.state before yielding.
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    test_app = create_app(db_url="", api_key="test-key")
    engine = create_engine_from_url(db_url)
    await init_db(engine)
    test_app.state.engine = engine
    yield test_app
    await engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key"}


@pytest.fixture
async def hive_with_readings(client, auth_headers):
    """Create a hive and insert readings directly via DB."""
    resp = await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )
    assert resp.status_code == 201
    return 1  # hive_id


async def _insert_readings(client, hive_id: int, count: int = 5):
    """Insert readings directly via the database engine."""
    engine = client._transport.app.state.engine
    async with AsyncSession(engine) as session:
        for i in range(count):
            reading = SensorReading(
                hive_id=hive_id,
                observed_at=f"2026-02-07T{10 + i:02d}:00:00.000Z",
                ingested_at=f"2026-02-07T{10 + i:02d}:00:00.100Z",
                weight_kg=30.0 + i,
                temp_c=35.0 + i * 0.5,
                humidity_pct=50.0 + i,
                pressure_hpa=1013.0,
                battery_v=3.7,
                sequence=i,
                flags=0,
                sender_mac="AA:BB:CC:DD:EE:FF",
            )
            session.add(reading)
        await session.commit()


async def test_readings_raw(client, auth_headers, hive_with_readings):
    await _insert_readings(client, hive_with_readings, count=5)
    resp = await client.get("/api/hives/1/readings", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == "raw"
    assert body["total"] == 5
    assert len(body["items"]) == 5
    # Ordered by observed_at DESC
    assert body["items"][0]["observed_at"] > body["items"][-1]["observed_at"]


async def test_readings_raw_with_time_range(client, auth_headers, hive_with_readings):
    await _insert_readings(client, hive_with_readings, count=5)
    resp = await client.get(
        "/api/hives/1/readings?start=2026-02-07T11:00:00.000Z&end=2026-02-07T13:00:00.000Z",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # 11:00, 12:00, and 13:00 (inclusive on both ends)


async def test_readings_hourly(client, auth_headers, hive_with_readings):
    await _insert_readings(client, hive_with_readings, count=5)
    resp = await client.get(
        "/api/hives/1/readings?interval=hourly", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == "hourly"
    # Each reading is in a different hour, so 5 buckets
    assert body["total"] == 5
    item = body["items"][0]
    assert "period_start" in item
    assert "avg_weight_kg" in item
    assert "count" in item


async def test_readings_daily(client, auth_headers, hive_with_readings):
    await _insert_readings(client, hive_with_readings, count=5)
    resp = await client.get(
        "/api/hives/1/readings?interval=daily", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == "daily"
    # All readings are on the same day
    assert body["total"] == 1
    assert body["items"][0]["count"] == 5


async def test_readings_pagination(client, auth_headers, hive_with_readings):
    await _insert_readings(client, hive_with_readings, count=5)
    resp = await client.get(
        "/api/hives/1/readings?limit=2&offset=0", headers=auth_headers
    )
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5


async def test_readings_latest(client, auth_headers, hive_with_readings):
    await _insert_readings(client, hive_with_readings, count=5)
    resp = await client.get("/api/hives/1/readings/latest", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed_at"] == "2026-02-07T14:00:00.000Z"  # The last one (10+4=14)


async def test_readings_latest_no_readings(client, auth_headers, hive_with_readings):
    resp = await client.get("/api/hives/1/readings/latest", headers=auth_headers)
    assert resp.status_code == 404


async def test_readings_hive_not_found(client, auth_headers):
    resp = await client.get("/api/hives/99/readings", headers=auth_headers)
    assert resp.status_code == 404


async def test_readings_empty(client, auth_headers, hive_with_readings):
    resp = await client.get("/api/hives/1/readings", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
