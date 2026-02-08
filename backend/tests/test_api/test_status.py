"""Tests for hub status endpoint."""

import pytest


async def test_status_no_auth_required(client):
    """Status endpoint should not require API key."""
    resp = await client.get("/api/hub/status")
    assert resp.status_code == 200


async def test_status_response_schema(client):
    """Status response should match HubStatusOut schema."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert "status" in body
    assert "uptime_sec" in body
    assert isinstance(body["uptime_sec"], int)
    assert "last_ingest_at" in body
    assert "mqtt_connected" in body
    assert "disk_free_mb" in body
    assert isinstance(body["disk_free_mb"], int)
    assert "hive_count" in body
    assert "reading_count_24h" in body
    assert "services" in body
    services = body["services"]
    assert "bridge" in services
    assert "worker" in services
    assert "mqtt" in services
    assert "api" in services


async def test_status_empty_db(client):
    """Status with empty DB should show zero counts."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["hive_count"] == 0
    assert body["reading_count_24h"] == 0
    assert body["last_ingest_at"] is None


async def test_status_with_data(client, auth_headers):
    """Status with data should reflect counts."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from waggle.models import Hive, SensorReading
    from waggle.utils.timestamps import utc_now

    # Create a hive via the API
    resp = await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )
    assert resp.status_code == 201

    # Insert a reading directly via the DB
    engine = client._transport.app.state.engine
    async with AsyncSession(engine) as session:
        reading = SensorReading(
            hive_id=1,
            observed_at=utc_now(),
            ingested_at=utc_now(),
            weight_kg=30.0,
            temp_c=35.0,
            humidity_pct=50.0,
            pressure_hpa=1013.0,
            battery_v=3.7,
            sequence=1,
            flags=0,
            sender_mac="AA:BB:CC:DD:EE:FF",
        )
        session.add(reading)
        await session.commit()

    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["hive_count"] == 1
    assert body["reading_count_24h"] == 1
    assert body["last_ingest_at"] is not None


async def test_status_ok(client):
    """Status should report ok."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["status"] == "ok"
