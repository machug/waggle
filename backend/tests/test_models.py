"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import Alert, Hive, SensorReading


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
        created_at="2026-02-07T18:25:00.000Z",
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
