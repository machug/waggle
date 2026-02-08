"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import (
    Alert,
    BeeCount,
    CameraNode,
    Hive,
    Inspection,
    MlDetection,
    Photo,
    SensorReading,
    SyncState,
)


@pytest.fixture
async def session(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(url, is_worker=False)
    await init_db(engine)
    async with AsyncSession(engine) as sess:
        yield sess
    await engine.dispose()


async def test_create_hive(session):
    hive = Hive(
        id=1,
        name="Test Hive",
        created_at="2026-02-07T18:00:00.000Z",
    )
    session.add(hive)
    await session.commit()
    await session.refresh(hive)
    assert hive.id == 1
    assert hive.name == "Test Hive"
    assert hive.last_seen_at is None


async def test_create_sensor_reading(session):
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    reading = SensorReading(
        hive_id=1,
        observed_at="2026-02-07T18:21:04.123Z",
        ingested_at="2026-02-07T18:21:04.200Z",
        weight_kg=32.12,
        temp_c=36.45,
        humidity_pct=51.2,
        pressure_hpa=1013.2,
        battery_v=3.71,
        sequence=1024,
        flags=0,
        sender_mac="AA:BB:CC:DD:EE:FF",
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    assert reading.id is not None
    assert reading.hive_id == 1


async def test_create_alert(session):
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    alert = Alert(
        hive_id=1,
        type="HIGH_TEMP",
        severity="medium",
        message="Temperature exceeds 40\u00b0C",
        observed_at="2026-02-07T18:25:00.000Z",
        created_at="2026-02-07T18:25:00.000Z",
        updated_at="2026-02-07T18:25:00.000Z",
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    assert alert.id is not None
    assert alert.acknowledged == 0


async def test_hive_id_check_constraint(session):
    """Hive id must be between 1 and 250."""
    hive = Hive(id=0, name="Bad", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    with pytest.raises(Exception):
        await session.commit()


async def test_reading_dedup_unique_index(session):
    """Duplicate (hive_id, sequence, observed_at) should raise."""
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    common = dict(
        hive_id=1,
        observed_at="2026-02-07T18:21:04.123Z",
        ingested_at="2026-02-07T18:21:04.200Z",
        weight_kg=32.0,
        temp_c=36.0,
        humidity_pct=50.0,
        pressure_hpa=1013.0,
        battery_v=3.7,
        sequence=100,
        flags=0,
        sender_mac="AA:BB:CC:DD:EE:FF",
    )
    session.add(SensorReading(**common))
    await session.commit()

    session.add(SensorReading(**common))
    with pytest.raises(Exception):
        await session.commit()


async def test_bee_count_model_fields():
    """BeeCount model exposes all expected columns."""
    columns = {c.name for c in BeeCount.__table__.columns}
    expected = {
        "id", "reading_id", "hive_id", "observed_at", "ingested_at",
        "period_ms", "bees_in", "bees_out", "net_out", "total_traffic",
        "lane_mask", "stuck_mask", "sequence", "flags", "sender_mac",
        "row_synced",
    }
    assert columns >= expected


async def test_phase3_camera_node_model(session):
    """CameraNode can be created and persisted."""
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    cam = CameraNode(
        device_id="cam-001",
        hive_id=1,
        api_key_hash="abc123hash",
        created_at="2026-02-07T18:00:00.000Z",
    )
    session.add(cam)
    await session.commit()
    await session.refresh(cam)
    assert cam.device_id == "cam-001"
    assert cam.hive_id == 1
    assert cam.last_seen_at is None
    assert cam.row_synced == 0


async def test_phase3_photo_model(session):
    """Photo can be created with correct defaults."""
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    cam = CameraNode(
        device_id="cam-001",
        hive_id=1,
        api_key_hash="abc123hash",
        created_at="2026-02-07T18:00:00.000Z",
    )
    session.add(cam)
    await session.commit()

    photo = Photo(
        hive_id=1,
        device_id="cam-001",
        boot_id=1,
        captured_at="2026-02-07T18:10:00.000Z",
        captured_at_source="device_ntp",
        sequence=1,
        photo_path="/photos/hive1/001.jpg",
        file_size_bytes=102400,
        sha256="a" * 64,
    )
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    assert photo.id is not None
    assert photo.ml_status == "pending"
    assert photo.ml_attempts == 0
    assert photo.width == 800
    assert photo.height == 600
    assert photo.row_synced == 0
    assert photo.file_synced == 0


async def test_phase3_ml_detection_model(session):
    """MlDetection can be created and persisted."""
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    cam = CameraNode(
        device_id="cam-001",
        hive_id=1,
        api_key_hash="abc123hash",
        created_at="2026-02-07T18:00:00.000Z",
    )
    session.add(cam)
    await session.commit()

    photo = Photo(
        hive_id=1,
        device_id="cam-001",
        boot_id=1,
        captured_at="2026-02-07T18:10:00.000Z",
        captured_at_source="device_ntp",
        sequence=1,
        photo_path="/photos/hive1/001.jpg",
        file_size_bytes=102400,
        sha256="a" * 64,
    )
    session.add(photo)
    await session.commit()
    await session.refresh(photo)

    detection = MlDetection(
        photo_id=photo.id,
        hive_id=1,
        detected_at="2026-02-07T18:10:05.000Z",
        top_class="varroa",
        top_confidence=0.92,
        inference_ms=150,
        model_hash="deadbeef" * 8,
    )
    session.add(detection)
    await session.commit()
    await session.refresh(detection)
    assert detection.id is not None
    assert detection.top_class == "varroa"
    assert detection.top_confidence == 0.92
    assert detection.varroa_count == 0
    assert detection.row_synced == 0


async def test_phase3_inspection_model(session):
    """Inspection uses UUID primary key."""
    hive = Hive(id=1, name="Test", created_at="2026-02-07T18:00:00.000Z")
    session.add(hive)
    await session.commit()

    inspection = Inspection(
        uuid="550e8400-e29b-41d4-a716-446655440000",
        hive_id=1,
        inspected_at="2026-02-07T12:00:00.000Z",
        created_at="2026-02-07T12:00:00.000Z",
        updated_at="2026-02-07T12:00:00.000Z",
    )
    session.add(inspection)
    await session.commit()
    await session.refresh(inspection)
    assert inspection.uuid == "550e8400-e29b-41d4-a716-446655440000"
    assert inspection.hive_id == 1
    assert inspection.queen_seen == 0
    assert inspection.brood_pattern is None
    assert inspection.row_synced == 0


async def test_phase3_sync_state_model(session):
    """SyncState stores key-value pairs."""
    state = SyncState(key="last_push", value="2026-02-07T18:00:00.000Z")
    session.add(state)
    await session.commit()
    await session.refresh(state)
    assert state.key == "last_push"
    assert state.value == "2026-02-07T18:00:00.000Z"


async def test_phase3_hive_row_synced():
    """Hive model has row_synced column."""
    columns = {c.name for c in Hive.__table__.columns}
    assert "row_synced" in columns


async def test_phase3_alert_expanded_types():
    """Alert type CHECK includes Phase 3 types like VARROA_DETECTED."""
    columns = {c.name for c in Alert.__table__.columns}
    assert "type" in columns
    # Verify the CHECK constraint includes the new types
    check_constraints = [
        c for c in Alert.__table__.constraints
        if hasattr(c, "name") and c.name == "ck_alert_type"
    ]
    assert len(check_constraints) == 1
    sql_text = str(check_constraints[0].sqltext)
    assert "VARROA_DETECTED" in sql_text
    assert "VARROA_HIGH_LOAD" in sql_text
    assert "VARROA_RISING" in sql_text
    assert "WASP_ATTACK" in sql_text
    assert "HIGH_HUMIDITY" in sql_text
    assert "LOW_HUMIDITY" in sql_text
    assert "RAPID_WEIGHT_LOSS" in sql_text


async def test_phase3_alert_new_columns():
    """Alert model has all Phase 3 columns."""
    columns = {c.name for c in Alert.__table__.columns}
    expected_new = {
        "observed_at", "notified_at", "updated_at", "source",
        "details_json", "row_synced",
    }
    assert columns >= expected_new
    # reading_id should no longer exist
    assert "reading_id" not in columns
