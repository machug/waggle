"""Tests for worker ingestion service."""


from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.config import Settings
from waggle.database import create_engine_from_url, init_db
from waggle.models import Hive, SensorReading
from waggle.services.alert_engine import AlertEngine
from waggle.services.ingestion import IngestionService
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
def settings():
    return Settings(API_KEY="test-key")


@pytest.fixture
async def service(engine, settings):
    alert_engine = AlertEngine(engine)
    return IngestionService(engine, settings, alert_engine)


@pytest.fixture
async def hive(engine):
    async with AsyncSession(engine) as session:
        h = Hive(id=1, name="Test", created_at=utc_now(), sender_mac="AA:BB:CC:DD:EE:FF")
        session.add(h)
        await session.commit()
    return 1


def _make_payload(hive_id=1, **overrides):
    """Make a valid MQTT sensor message payload."""
    defaults = {
        "schema_version": 1,
        "hive_id": hive_id,
        "msg_type": 1,
        "sequence": 100,
        "weight_g": 32120,
        "temp_c_x100": 3645,
        "humidity_x100": 5120,
        "pressure_hpa_x10": 10132,
        "battery_mv": 3710,
        "flags": 0,
        "sender_mac": "AA:BB:CC:DD:EE:FF",
        "observed_at": utc_now(),
    }
    defaults.update(overrides)
    return defaults


# Valid ingestion
async def test_valid_message(service, hive):
    result = await service.process_message("waggle/1/sensors", _make_payload())
    assert result is True


async def test_valid_message_stored_in_db(service, hive, engine):
    await service.process_message("waggle/1/sensors", _make_payload())
    async with AsyncSession(engine) as session:
        count = await session.scalar(select(func.count()).select_from(SensorReading))
    assert count == 1


# Validation failures
async def test_bad_schema_version(service, hive):
    result = await service.process_message("waggle/1/sensors", _make_payload(schema_version=99))
    assert result is False


async def test_topic_hive_mismatch(service, hive):
    result = await service.process_message("waggle/2/sensors", _make_payload(hive_id=1))
    assert result is False


async def test_unknown_hive(service):
    result = await service.process_message("waggle/99/sensors", _make_payload(hive_id=99))
    assert result is False


async def test_bad_msg_type(service, hive):
    result = await service.process_message("waggle/1/sensors", _make_payload(msg_type=99))
    assert result is False


async def test_mac_mismatch(service, hive):
    result = await service.process_message(
        "waggle/1/sensors", _make_payload(sender_mac="11:22:33:44:55:66")
    )
    assert result is False


async def test_bad_timestamp(service, hive):
    result = await service.process_message(
        "waggle/1/sensors", _make_payload(observed_at="not-a-time")
    )
    assert result is False


async def test_future_timestamp(service, hive):
    future = (datetime.now(UTC) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    result = await service.process_message(
        "waggle/1/sensors", _make_payload(observed_at=future)
    )
    assert result is False


# Unit conversion
async def test_unit_conversion(service, hive, engine):
    await service.process_message("waggle/1/sensors", _make_payload())
    async with AsyncSession(engine) as session:
        reading = (await session.execute(select(SensorReading))).scalar_one()
    assert abs(reading.weight_kg - 32.12) < 0.01
    assert abs(reading.temp_c - 36.45) < 0.01
    assert abs(reading.humidity_pct - 51.2) < 0.1
    assert abs(reading.pressure_hpa - 1013.2) < 0.1
    assert abs(reading.battery_v - 3.71) < 0.01


# Error flag handling
async def test_hx711_error_nulls_weight(service, hive, engine):
    await service.process_message(
        "waggle/1/sensors", _make_payload(flags=0b00001000)
    )  # bit 3
    async with AsyncSession(engine) as session:
        reading = (await session.execute(select(SensorReading))).scalar_one()
    assert reading.weight_kg is None


async def test_bme280_error_nulls_env(service, hive, engine):
    await service.process_message(
        "waggle/1/sensors", _make_payload(flags=0b00010000)
    )  # bit 4
    async with AsyncSession(engine) as session:
        reading = (await session.execute(select(SensorReading))).scalar_one()
    assert reading.temp_c is None
    assert reading.humidity_pct is None
    assert reading.pressure_hpa is None


async def test_battery_error_nulls_battery(service, hive, engine):
    await service.process_message(
        "waggle/1/sensors", _make_payload(flags=0b00100000)
    )  # bit 5
    async with AsyncSession(engine) as session:
        reading = (await session.execute(select(SensorReading))).scalar_one()
    assert reading.battery_v is None


# Range validation
async def test_range_violation_drops(service, hive):
    # weight_g=999999 -> weight_kg=999.999, exceeds 200
    result = await service.process_message(
        "waggle/1/sensors", _make_payload(weight_g=999999)
    )
    assert result is False


# Dedup
async def test_dedup_same_sequence(service, hive):
    result1 = await service.process_message(
        "waggle/1/sensors", _make_payload(sequence=100)
    )
    result2 = await service.process_message(
        "waggle/1/sensors", _make_payload(sequence=100, observed_at=utc_now())
    )
    assert result1 is True
    assert result2 is False  # Deduped by in-memory cache


async def test_first_boot_clears_dedup(service, hive):
    # First message
    await service.process_message("waggle/1/sensors", _make_payload(sequence=100))
    # Second with FIRST_BOOT flag (bit 1) and same sequence - should NOT be deduped
    result = await service.process_message(
        "waggle/1/sensors",
        _make_payload(sequence=100, flags=0b00000010, observed_at=utc_now()),
    )
    assert result is True


# last_seen_at update
async def test_last_seen_at_updated(service, hive, engine):
    await service.process_message("waggle/1/sensors", _make_payload())
    async with AsyncSession(engine) as session:
        h = (await session.execute(select(Hive).where(Hive.id == 1))).scalar_one()
    assert h.last_seen_at is not None
