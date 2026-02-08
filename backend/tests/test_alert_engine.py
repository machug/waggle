"""Tests for alert engine."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import Alert, Hive, SensorReading
from waggle.services.alert_engine import AlertEngine
from waggle.utils.timestamps import utc_now


@pytest.fixture
async def engine(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    eng = create_engine_from_url(url)
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def alert_engine(engine):
    return AlertEngine(engine)


@pytest.fixture
async def hive_with_reading(engine):
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test", created_at=utc_now())
        session.add(hive)
        await session.commit()
    return 1


async def _insert_reading(engine, hive_id, **overrides):
    """Insert a reading and return its id."""
    defaults = dict(
        hive_id=hive_id,
        observed_at=utc_now(),
        ingested_at=utc_now(),
        weight_kg=30.0,
        temp_c=35.0,
        humidity_pct=50.0,
        pressure_hpa=1013.0,
        battery_v=3.7,
        sequence=0,
        flags=0,
        sender_mac="AA:BB:CC:DD:EE:FF",
    )
    defaults.update(overrides)
    async with AsyncSession(engine) as session:
        reading = SensorReading(**defaults)
        session.add(reading)
        await session.commit()
        await session.refresh(reading)
        return reading.id


# HIGH_TEMP tests
async def test_high_temp_fires(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, temp_c=41.0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 41.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert any(a["type"] == "HIGH_TEMP" for a in alerts)


async def test_high_temp_no_fire_at_boundary(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, temp_c=40.0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 40.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "HIGH_TEMP" for a in alerts)


async def test_high_temp_null_skipped(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, temp_c=None)
    reading = {
        "weight_kg": 30.0,
        "temp_c": None,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "HIGH_TEMP" for a in alerts)


# LOW_TEMP tests
async def test_low_temp_fires(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, temp_c=4.9)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 4.9,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert any(a["type"] == "LOW_TEMP" for a in alerts)


async def test_low_temp_no_fire_at_boundary(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, temp_c=5.0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 5.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "LOW_TEMP" for a in alerts)


async def test_low_temp_null_skipped(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, temp_c=None)
    reading = {
        "weight_kg": 30.0,
        "temp_c": None,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "LOW_TEMP" for a in alerts)


# LOW_BATTERY tests
async def test_low_battery_fires(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, battery_v=3.2)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.2,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert any(a["type"] == "LOW_BATTERY" for a in alerts)


async def test_low_battery_no_fire_at_boundary(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, battery_v=3.3)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.3,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "LOW_BATTERY" for a in alerts)


async def test_low_battery_null_skipped(engine, alert_engine, hive_with_reading):
    await _insert_reading(engine, 1, battery_v=None)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": None,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "LOW_BATTERY" for a in alerts)


# COOLDOWN tests
async def test_cooldown_suppresses(engine, alert_engine, hive_with_reading):
    # First alert fires
    await _insert_reading(engine, 1, temp_c=41.0, sequence=0)
    reading1 = {
        "weight_kg": 30.0,
        "temp_c": 41.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts1 = await alert_engine.check_reading(1, reading1)
    assert any(a["type"] == "HIGH_TEMP" for a in alerts1)
    # Second alert suppressed by cooldown
    await _insert_reading(engine, 1, temp_c=42.0, sequence=1)
    reading2 = {
        "weight_kg": 30.0,
        "temp_c": 42.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts2 = await alert_engine.check_reading(1, reading2)
    assert not any(a["type"] == "HIGH_TEMP" for a in alerts2)


async def test_cooldown_different_types_independent(engine, alert_engine, hive_with_reading):
    """Cooldown for one alert type should not suppress a different type."""
    await _insert_reading(engine, 1, temp_c=41.0, battery_v=3.2, sequence=0)
    reading1 = {
        "weight_kg": 30.0,
        "temp_c": 41.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.2,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts1 = await alert_engine.check_reading(1, reading1)
    assert any(a["type"] == "HIGH_TEMP" for a in alerts1)
    assert any(a["type"] == "LOW_BATTERY" for a in alerts1)

    # Second reading: HIGH_TEMP cooldown active but LOW_BATTERY also in cooldown
    await _insert_reading(engine, 1, temp_c=42.0, battery_v=3.1, sequence=1)
    reading2 = {
        "weight_kg": 30.0,
        "temp_c": 42.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.1,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts2 = await alert_engine.check_reading(1, reading2)
    # Both should be suppressed
    assert not any(a["type"] == "HIGH_TEMP" for a in alerts2)
    assert not any(a["type"] == "LOW_BATTERY" for a in alerts2)


# POSSIBLE_SWARM tests
async def test_swarm_fires(engine, alert_engine, hive_with_reading):
    now = datetime.now(UTC)
    # Insert 6 readings over the past hour with stable weight, then a drop
    for i in range(6):
        ts = (now - timedelta(minutes=50 - i * 10)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        weight = 35.0 if i < 5 else 32.0  # Last one drops 3kg
        await _insert_reading(
            engine, 1, weight_kg=weight, observed_at=ts, ingested_at=ts, sequence=i
        )

    observed = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    reading = {
        "weight_kg": 32.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    await _insert_reading(
        engine, 1, weight_kg=32.0, observed_at=observed, ingested_at=observed, sequence=6
    )
    alerts = await alert_engine.check_reading(1, reading)
    assert any(a["type"] == "POSSIBLE_SWARM" for a in alerts)


async def test_swarm_insufficient_data(engine, alert_engine, hive_with_reading):
    """Less than 5 readings = no swarm alert."""
    await _insert_reading(engine, 1, weight_kg=30.0, sequence=0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "POSSIBLE_SWARM" for a in alerts)


async def test_swarm_no_fire_small_drop(engine, alert_engine, hive_with_reading):
    """Weight drop of exactly 2kg should NOT fire (must be >2kg)."""
    now = datetime.now(UTC)
    for i in range(6):
        ts = (now - timedelta(minutes=50 - i * 10)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        await _insert_reading(
            engine, 1, weight_kg=35.0, observed_at=ts, ingested_at=ts, sequence=i
        )

    observed = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    reading = {
        "weight_kg": 33.0,  # Only 2kg drop, not >2kg
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    await _insert_reading(
        engine, 1, weight_kg=33.0, observed_at=observed, ingested_at=observed, sequence=6
    )
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "POSSIBLE_SWARM" for a in alerts)


async def test_swarm_null_weight_skipped(engine, alert_engine, hive_with_reading):
    """Null weight_kg should not trigger swarm check."""
    await _insert_reading(engine, 1, weight_kg=None, sequence=0)
    reading = {
        "weight_kg": None,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "POSSIBLE_SWARM" for a in alerts)


# NO_DATA tests
async def test_no_data_fires(engine, alert_engine):
    """Hive with stale last_seen_at should trigger NO_DATA."""
    stale = (datetime.now(UTC) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Stale", created_at=utc_now(), last_seen_at=stale)
        session.add(hive)
        await session.commit()
    alerts = await alert_engine.check_no_data()
    assert any(a["type"] == "NO_DATA" for a in alerts)


async def test_no_data_not_stale(engine, alert_engine):
    """Hive with recent last_seen_at should NOT trigger NO_DATA."""
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Fresh", created_at=utc_now(), last_seen_at=utc_now())
        session.add(hive)
        await session.commit()
    alerts = await alert_engine.check_no_data()
    assert not any(a["type"] == "NO_DATA" for a in alerts)


async def test_no_data_null_last_seen_skipped(engine, alert_engine):
    """Hive with NULL last_seen_at should NOT trigger NO_DATA (never connected)."""
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="NeverSeen", created_at=utc_now(), last_seen_at=None)
        session.add(hive)
        await session.commit()
    alerts = await alert_engine.check_no_data()
    assert not any(a["type"] == "NO_DATA" for a in alerts)


async def test_no_data_cooldown_suppresses(engine, alert_engine):
    """NO_DATA should not fire twice within 60-minute cooldown."""
    stale = (datetime.now(UTC) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Stale", created_at=utc_now(), last_seen_at=stale)
        session.add(hive)
        await session.commit()

    alerts1 = await alert_engine.check_no_data()
    assert any(a["type"] == "NO_DATA" for a in alerts1)

    # Second call should be suppressed by cooldown
    alerts2 = await alert_engine.check_no_data()
    assert not any(a["type"] == "NO_DATA" for a in alerts2)


# Alert content tests
async def test_alert_has_correct_fields(engine, alert_engine, hive_with_reading):
    """Fired alert dict should contain expected keys."""
    await _insert_reading(engine, 1, temp_c=41.0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 41.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    high_temp = [a for a in alerts if a["type"] == "HIGH_TEMP"][0]
    assert high_temp["severity"] == "medium"
    assert high_temp["hive_id"] == 1
    assert "observed_at" in high_temp
    assert "message" in high_temp
    assert len(high_temp["message"]) >= 1


async def test_multiple_alerts_fire_simultaneously(engine, alert_engine, hive_with_reading):
    """A reading can trigger multiple alert types at once."""
    await _insert_reading(engine, 1, temp_c=41.0, battery_v=3.2, sequence=0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 41.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.2,
        "observed_at": utc_now(),
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    types = {a["type"] for a in alerts}
    assert "HIGH_TEMP" in types
    assert "LOW_BATTERY" in types


async def test_alert_persisted_to_db(engine, alert_engine, hive_with_reading):
    """Fired alerts should be persisted in the alerts table."""
    await _insert_reading(engine, 1, temp_c=41.0)
    reading = {
        "weight_kg": 30.0,
        "temp_c": 41.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": utc_now(),
        "flags": 0,
    }
    await alert_engine.check_reading(1, reading)

    async with AsyncSession(engine) as session:
        from sqlalchemy import select

        result = await session.execute(select(Alert))
        db_alerts = result.scalars().all()
        assert len(db_alerts) == 1
        assert db_alerts[0].type == "HIGH_TEMP"
        assert db_alerts[0].severity == "medium"
        assert db_alerts[0].hive_id == 1
        assert db_alerts[0].observed_at is not None
