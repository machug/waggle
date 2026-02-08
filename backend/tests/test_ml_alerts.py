"""Tests for Phase 3 ML-based alert rules.

Tests cover: VARROA_DETECTED, VARROA_HIGH_LOAD, VARROA_RISING, WASP_ATTACK,
cooldown suppression, and _fire method without reading_id.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import CameraNode, Hive, MlDetection, Photo
from waggle.services.alert_engine import AlertEngine
from waggle.utils.timestamps import utc_now


def _ts(dt: datetime) -> str:
    """Format a datetime as canonical ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@pytest.fixture
async def engine(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    eng = create_engine_from_url(db_url)
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def alert_engine(engine):
    return AlertEngine(engine)


@pytest.fixture
async def engine_with_hive(engine):
    """Create a hive + camera node for ML detection tests."""
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test Hive", created_at=utc_now())
        session.add(hive)
        await session.flush()

        key_hash = bcrypt.hashpw(b"test-key", bcrypt.gensalt()).decode()
        node = CameraNode(
            device_id="cam-01",
            hive_id=1,
            api_key_hash=key_hash,
            created_at=utc_now(),
        )
        session.add(node)
        await session.commit()
    return engine


async def _insert_photo(engine, hive_id=1, device_id="cam-01", **overrides):
    """Insert a photo and return its id."""
    defaults = dict(
        hive_id=hive_id,
        device_id=device_id,
        boot_id=1,
        captured_at=utc_now(),
        captured_at_source="device_ntp",
        ingested_at=utc_now(),
        sequence=0,
        photo_path="/tmp/test.jpg",
        file_size_bytes=1024,
        sha256="a" * 64,
        width=800,
        height=600,
        ml_status="completed",
        ml_attempts=1,
        inference_ms=100,
    )
    defaults.update(overrides)
    # Remove non-Photo fields that might be passed
    defaults.pop("inference_ms", None)
    async with AsyncSession(engine) as session:
        photo = Photo(**defaults)
        session.add(photo)
        await session.commit()
        await session.refresh(photo)
        return photo.id


async def _insert_detection(engine, photo_id, hive_id=1, **overrides):
    """Insert an MlDetection and return its id."""
    defaults = dict(
        photo_id=photo_id,
        hive_id=hive_id,
        detected_at=utc_now(),
        top_class="normal",
        top_confidence=0.9,
        detections_json="[]",
        varroa_count=0,
        pollen_count=0,
        wasp_count=0,
        bee_count=10,
        varroa_max_confidence=0.0,
        inference_ms=100,
        model_version="yolov8n-waggle-v1",
        model_hash="abc123",
    )
    defaults.update(overrides)
    async with AsyncSession(engine) as session:
        detection = MlDetection(**defaults)
        session.add(detection)
        await session.commit()
        await session.refresh(detection)
        return detection.id


# ---- VARROA_DETECTED tests ----


async def test_varroa_detected_alert(engine_with_hive, alert_engine):
    """Detection with varroa_max_confidence=0.8 triggers VARROA_DETECTED."""
    engine = engine_with_hive
    photo_id = await _insert_photo(engine, sequence=1, sha256="b" * 64)
    await _insert_detection(
        engine,
        photo_id,
        varroa_max_confidence=0.8,
        varroa_count=2,
        top_class="varroa",
        top_confidence=0.8,
    )

    alerts = await alert_engine.check_ml_alerts(1)
    varroa = [a for a in alerts if a["type"] == "VARROA_DETECTED"]
    assert len(varroa) == 1
    assert varroa[0]["severity"] == "low"
    assert varroa[0]["hive_id"] == 1


async def test_varroa_detected_below_threshold(engine_with_hive, alert_engine):
    """Detection with varroa_max_confidence=0.5 does NOT trigger."""
    engine = engine_with_hive
    photo_id = await _insert_photo(engine, sequence=2, sha256="c" * 64)
    await _insert_detection(
        engine,
        photo_id,
        varroa_max_confidence=0.5,
        varroa_count=1,
        top_class="varroa",
        top_confidence=0.5,
    )

    alerts = await alert_engine.check_ml_alerts(1)
    assert not any(a["type"] == "VARROA_DETECTED" for a in alerts)


# ---- VARROA_HIGH_LOAD tests ----


async def test_varroa_high_load_alert(engine_with_hive, alert_engine):
    """Daily ratio > 3.0 triggers VARROA_HIGH_LOAD (critical)."""
    engine = engine_with_hive
    now = datetime.now(UTC)

    # Insert multiple detections today with high varroa ratio
    # 5 varroa / 100 bees total = 5.0 mites per 100 bees > 3.0
    for i in range(5):
        ts = _ts(now - timedelta(hours=i))
        photo_id = await _insert_photo(
            engine,
            sequence=10 + i,
            sha256=f"{'d' * 62}{i:02d}",
            captured_at=ts,
            ingested_at=ts,
        )
        await _insert_detection(
            engine,
            photo_id,
            detected_at=ts,
            varroa_count=1,
            bee_count=20,
            varroa_max_confidence=0.8,
        )

    alerts = await alert_engine.check_ml_alerts(1)
    high_load = [a for a in alerts if a["type"] == "VARROA_HIGH_LOAD"]
    assert len(high_load) == 1
    assert high_load[0]["severity"] == "critical"


# ---- VARROA_RISING tests ----


async def test_varroa_rising_alert(engine_with_hive, alert_engine):
    """7-day rising slope > 0.3 and ratio > 1.0 triggers VARROA_RISING."""
    engine = engine_with_hive
    now = datetime.now(UTC)

    # Create detections over 7 days with increasing varroa ratio
    # Day 0: 0 varroa/100 bees, Day 6: ~3.0 varroa/100 bees
    # slope = ~0.5/day which is > 0.3
    for day in range(7):
        day_base = now - timedelta(days=6 - day)
        day_base = day_base.replace(hour=12, minute=0, second=0, microsecond=0)
        ts = _ts(day_base)
        varroa_count = day  # 0, 1, 2, 3, 4, 5, 6
        photo_id = await _insert_photo(
            engine,
            sequence=20 + day,
            sha256=f"{'e' * 62}{day:02d}",
            captured_at=ts,
            ingested_at=ts,
        )
        await _insert_detection(
            engine,
            photo_id,
            detected_at=ts,
            varroa_count=varroa_count,
            bee_count=100,
            varroa_max_confidence=0.5,
        )

    alerts = await alert_engine.check_ml_alerts(1)
    rising = [a for a in alerts if a["type"] == "VARROA_RISING"]
    assert len(rising) == 1
    assert rising[0]["severity"] == "high"


# ---- WASP_ATTACK tests ----


async def test_wasp_attack_alert(engine_with_hive, alert_engine):
    """3+ wasp detections in 10 min triggers WASP_ATTACK."""
    engine = engine_with_hive
    now = datetime.now(UTC)

    # Insert 3 detections with wasps in last 10 minutes
    for i in range(3):
        ts = _ts(now - timedelta(minutes=i * 2))
        photo_id = await _insert_photo(
            engine,
            sequence=30 + i,
            sha256=f"{'f' * 62}{i:02d}",
            captured_at=ts,
            ingested_at=ts,
        )
        await _insert_detection(
            engine,
            photo_id,
            detected_at=ts,
            wasp_count=1,
            bee_count=50,
        )

    alerts = await alert_engine.check_ml_alerts(1)
    wasp = [a for a in alerts if a["type"] == "WASP_ATTACK"]
    assert len(wasp) == 1
    assert wasp[0]["severity"] == "high"


# ---- Cooldown tests ----


async def test_ml_alert_cooldown(engine_with_hive, alert_engine):
    """Alert not re-fired within cooldown period."""
    engine = engine_with_hive

    # First detection triggers alert
    photo_id1 = await _insert_photo(engine, sequence=40, sha256="g" * 64)
    await _insert_detection(
        engine,
        photo_id1,
        varroa_max_confidence=0.85,
        varroa_count=3,
        top_class="varroa",
        top_confidence=0.85,
    )

    alerts1 = await alert_engine.check_ml_alerts(1)
    assert any(a["type"] == "VARROA_DETECTED" for a in alerts1)

    # Second detection within cooldown should NOT trigger
    photo_id2 = await _insert_photo(engine, sequence=41, sha256="h" * 64)
    await _insert_detection(
        engine,
        photo_id2,
        varroa_max_confidence=0.9,
        varroa_count=4,
        top_class="varroa",
        top_confidence=0.9,
    )

    alerts2 = await alert_engine.check_ml_alerts(1)
    assert not any(a["type"] == "VARROA_DETECTED" for a in alerts2)


# ---- _fire method fix test ----


async def test_fire_method_no_reading_id(engine_with_hive, alert_engine):
    """Verify _fire works without reading_id (the Phase 3 fix)."""
    engine = engine_with_hive
    async with AsyncSession(engine) as session:
        alert_dict = await alert_engine._fire(
            session,
            1,
            "HIGH_TEMP",
            "medium",
            "Test alert message",
            observed_at=utc_now(),
        )
        await session.commit()

    assert alert_dict["id"] is not None
    assert alert_dict["hive_id"] == 1
    assert alert_dict["type"] == "HIGH_TEMP"
    assert alert_dict["severity"] == "medium"
    assert "reading_id" not in alert_dict
    assert "observed_at" in alert_dict
    assert "created_at" in alert_dict
