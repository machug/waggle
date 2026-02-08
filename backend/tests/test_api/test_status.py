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


# --- Phase 3 ML & sync fields ---


async def test_status_has_phase3_fields(client):
    """Status response includes Phase 3 ML and sync fields."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert "photos_24h" in body
    assert "ml_queue_depth" in body
    assert "detections_24h" in body
    assert "sync_pending_rows" in body
    assert "sync_pending_files" in body


async def test_status_phase3_fields_empty_db(client):
    """Phase 3 fields are zero with empty DB."""
    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["photos_24h"] == 0
    assert body["ml_queue_depth"] == 0
    assert body["detections_24h"] == 0
    assert body["sync_pending_rows"] == 0
    assert body["sync_pending_files"] == 0


async def test_status_photos_24h(client, auth_headers):
    """photos_24h counts photos ingested in last 24 hours."""
    import hashlib

    from sqlalchemy.ext.asyncio import AsyncSession

    from waggle.models import CameraNode, Photo
    from waggle.utils.timestamps import utc_now

    await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )

    engine = client._transport.app.state.engine
    async with AsyncSession(engine) as session:
        cam = CameraNode(
            device_id="cam-001",
            hive_id=1,
            api_key_hash="fakehash",
            created_at=utc_now(),
        )
        session.add(cam)
        await session.flush()
        photo = Photo(
            hive_id=1,
            device_id="cam-001",
            boot_id=1,
            captured_at=utc_now(),
            captured_at_source="device_ntp",
            ingested_at=utc_now(),
            sequence=1,
            photo_path="/photos/test.jpg",
            file_size_bytes=1024,
            sha256=hashlib.sha256(b"test").hexdigest(),
            width=800,
            height=600,
        )
        session.add(photo)
        await session.commit()

    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["photos_24h"] == 1
    assert body["ml_queue_depth"] == 1  # default ml_status is "pending"
    assert body["sync_pending_files"] == 1  # default file_synced is 0


async def test_status_detections_24h(client, auth_headers):
    """detections_24h counts ML detections in last 24 hours."""
    import hashlib

    from sqlalchemy.ext.asyncio import AsyncSession

    from waggle.models import CameraNode, MlDetection, Photo
    from waggle.utils.timestamps import utc_now

    await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )

    engine = client._transport.app.state.engine
    async with AsyncSession(engine) as session:
        cam = CameraNode(
            device_id="cam-001",
            hive_id=1,
            api_key_hash="fakehash",
            created_at=utc_now(),
        )
        session.add(cam)
        await session.flush()
        photo = Photo(
            hive_id=1,
            device_id="cam-001",
            boot_id=1,
            captured_at=utc_now(),
            captured_at_source="device_ntp",
            ingested_at=utc_now(),
            sequence=1,
            photo_path="/photos/test.jpg",
            file_size_bytes=1024,
            sha256=hashlib.sha256(b"test").hexdigest(),
            width=800,
            height=600,
            ml_status="completed",
        )
        session.add(photo)
        await session.flush()
        detection = MlDetection(
            photo_id=photo.id,
            hive_id=1,
            detected_at=utc_now(),
            top_class="normal",
            top_confidence=0.95,
            detections_json="[]",
            inference_ms=150,
            model_version="yolov8n-waggle-v1",
            model_hash=hashlib.sha256(b"model").hexdigest(),
        )
        session.add(detection)
        await session.commit()

    resp = await client.get("/api/hub/status")
    body = resp.json()
    assert body["detections_24h"] == 1
    assert body["ml_queue_depth"] == 0  # photo is "completed"


async def test_status_sync_pending_rows(client, auth_headers):
    """sync_pending_rows counts unsynced rows across all tables."""
    await client.post(
        "/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers
    )

    resp = await client.get("/api/hub/status")
    body = resp.json()
    # The hive we just created has row_synced=0 by default
    assert body["sync_pending_rows"] >= 1
