"""Tests for Phase 2 dual-table ingestion (sensor_readings + bee_counts)."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.config import Settings
from waggle.database import create_engine_from_url, init_db
from waggle.models import BeeCount, Hive, SensorReading
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


def _make_phase2_payload(hive_id=1, **overrides):
    """Make a valid Phase 2 MQTT sensor+traffic message payload."""
    defaults = {
        "schema_version": 2,
        "hive_id": hive_id,
        "msg_type": 2,
        "sequence": 100,
        "weight_g": 32120,
        "temp_c_x100": 3645,
        "humidity_x100": 5120,
        "pressure_hpa_x10": 10132,
        "battery_mv": 3710,
        "flags": 0,
        "sender_mac": "AA:BB:CC:DD:EE:FF",
        "observed_at": utc_now(),
        # Phase 2 traffic fields
        "bees_in": 100,
        "bees_out": 150,
        "period_ms": 60000,
        "lane_mask": 15,
        "stuck_mask": 0,
    }
    defaults.update(overrides)
    return defaults


async def test_phase2_dual_insert(service, hive, engine):
    """schema_version=2, msg_type=2 with traffic fields inserts into BOTH tables."""
    payload = _make_phase2_payload()
    result = await service.process_message("waggle/1/sensors", payload)
    assert result is True

    async with AsyncSession(engine) as session:
        # Verify sensor_readings row
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 1

        reading = (await session.execute(select(SensorReading))).scalar_one()

        # Verify bee_counts row
        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 1

        bee_count = (await session.execute(select(BeeCount))).scalar_one()

        # Verify FK and field values
        assert bee_count.reading_id == reading.id
        assert bee_count.hive_id == 1
        assert bee_count.observed_at == reading.observed_at
        assert bee_count.period_ms == 60000
        assert bee_count.bees_in == 100
        assert bee_count.bees_out == 150
        assert bee_count.lane_mask == 15
        assert bee_count.stuck_mask == 0
        assert bee_count.sequence == 100
        assert bee_count.flags == 0
        assert bee_count.sender_mac == "AA:BB:CC:DD:EE:FF"


async def test_phase2_msg_type1_no_bee_counts(service, hive, engine):
    """schema_version=2, msg_type=1 inserts into sensor_readings only, no bee_counts."""
    payload = _make_phase2_payload(msg_type=1)
    result = await service.process_message("waggle/1/sensors", payload)
    assert result is True

    async with AsyncSession(engine) as session:
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 1

        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 0


async def test_phase1_backward_compat(service, hive, engine):
    """schema_version=1, msg_type=1 inserts sensor_readings only, no bee_counts."""
    payload = {
        "schema_version": 1,
        "hive_id": 1,
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
    result = await service.process_message("waggle/1/sensors", payload)
    assert result is True

    async with AsyncSession(engine) as session:
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 1

        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 0


async def test_traffic_validation_failure_saves_sensor_only(service, hive, engine):
    """msg_type=2 but invalid traffic (bees_in=-1) saves sensor_readings, skips bee_counts."""
    payload = _make_phase2_payload(bees_in=-1)
    result = await service.process_message("waggle/1/sensors", payload)
    assert result is True

    async with AsyncSession(engine) as session:
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 1

        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 0


async def test_traffic_validation_failure_period_zero(service, hive, engine):
    """msg_type=2 but invalid traffic (period_ms=0) saves sensor_readings, skips bee_counts."""
    payload = _make_phase2_payload(period_ms=0)
    result = await service.process_message("waggle/1/sensors", payload)
    assert result is True

    async with AsyncSession(engine) as session:
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 1

        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 0


async def test_dedup_skips_both_tables(service, hive, engine):
    """msg_type=2, same sequence twice: first inserts both, second deduped (no new rows)."""
    payload1 = _make_phase2_payload(sequence=200)
    result1 = await service.process_message("waggle/1/sensors", payload1)
    assert result1 is True

    payload2 = _make_phase2_payload(sequence=200, observed_at=utc_now())
    result2 = await service.process_message("waggle/1/sensors", payload2)
    assert result2 is False

    async with AsyncSession(engine) as session:
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 1

        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 1


async def test_first_boot_clears_dedup_dual(service, hive, engine):
    """msg_type=2 with FIRST_BOOT flag clears dedup cache, both tables inserted."""
    # First message
    payload1 = _make_phase2_payload(sequence=300)
    result1 = await service.process_message("waggle/1/sensors", payload1)
    assert result1 is True

    # Second with FIRST_BOOT flag (bit 1) and same sequence - should NOT be deduped
    payload2 = _make_phase2_payload(
        sequence=300, flags=0b00000010, observed_at=utc_now()
    )
    result2 = await service.process_message("waggle/1/sensors", payload2)
    assert result2 is True

    async with AsyncSession(engine) as session:
        sr_count = await session.scalar(select(func.count()).select_from(SensorReading))
        assert sr_count == 2

        bc_count = await session.scalar(select(func.count()).select_from(BeeCount))
        assert bc_count == 2


async def test_traffic_fields_passed_to_alert_engine(service, hive, engine):
    """msg_type=2: verify converted dict passed to alert_engine.check_reading() has traffic."""
    payload = _make_phase2_payload()

    with patch.object(service.alert_engine, "check_reading", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = []
        result = await service.process_message("waggle/1/sensors", payload)
        assert result is True

        mock_check.assert_called_once()
        call_args = mock_check.call_args
        converted = call_args[0][2]  # Third positional arg is the converted dict

        assert converted["bees_in"] == 100
        assert converted["bees_out"] == 150
        assert converted["period_ms"] == 60000
        assert converted["lane_mask"] == 15
        assert converted["stuck_mask"] == 0
