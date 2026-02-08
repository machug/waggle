"""Tests for hub status endpoint."""



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

    from waggle.models import SensorReading
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


# --- Phase 2 traffic fields ---


async def test_status_has_traffic_fields(client):
    """Status response includes Phase 2 traffic fields."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert "traffic_readings_24h" in body
    assert "phase2_nodes_active" in body
    assert "stuck_lanes_total" in body


async def test_status_traffic_fields_empty_db(client):
    """Traffic fields are zero with empty DB."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["traffic_readings_24h"] == 0
    assert body["phase2_nodes_active"] == 0
    assert body["stuck_lanes_total"] == 0


async def test_status_traffic_readings_24h(client, auth_headers):
    """traffic_readings_24h counts bee_counts in last 24 hours."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from waggle.models import BeeCount, SensorReading
    from waggle.utils.timestamps import utc_now

    await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )

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
        await session.flush()
        bc = BeeCount(
            reading_id=reading.id,
            hive_id=1,
            observed_at=reading.observed_at,
            ingested_at=reading.ingested_at,
            period_ms=60000,
            bees_in=100,
            bees_out=150,
            lane_mask=15,
            stuck_mask=0,
            sequence=1,
            flags=0,
            sender_mac="AA:BB:CC:DD:EE:FF",
        )
        session.add(bc)
        await session.commit()

    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["traffic_readings_24h"] == 1
    assert body["phase2_nodes_active"] == 1


async def test_status_stuck_lanes(client, auth_headers):
    """stuck_lanes_total counts stuck lanes from recent readings."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from waggle.models import BeeCount, SensorReading
    from waggle.utils.timestamps import utc_now

    await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )

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
        await session.flush()
        bc = BeeCount(
            reading_id=reading.id,
            hive_id=1,
            observed_at=reading.observed_at,
            ingested_at=reading.ingested_at,
            period_ms=60000,
            bees_in=50,
            bees_out=60,
            lane_mask=15,
            stuck_mask=3,  # 2 stuck lanes (bits 0,1)
            sequence=1,
            flags=0,
            sender_mac="AA:BB:CC:DD:EE:FF",
        )
        session.add(bc)
        await session.commit()

    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["stuck_lanes_total"] == 2  # bit_count(3) = 2
