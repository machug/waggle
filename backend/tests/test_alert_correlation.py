"""Tests for Phase 2 correlation alert rules.

Tests cover: POSSIBLE_SWARM (correlation + fallback), ABSCONDING, ROBBING,
LOW_ACTIVITY, flag exclusion, and cooldown suppression.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import BeeCount, Hive, SensorReading
from waggle.services.alert_engine import AlertEngine
from waggle.utils.timestamps import utc_now


def _ts(dt: datetime) -> str:
    """Format a datetime as canonical ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


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
    """Insert a sensor reading and return its id."""
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


async def _insert_reading_with_traffic(
    engine,
    hive_id,
    bees_in=100,
    bees_out=120,
    period_ms=60000,
    lane_mask=15,
    stuck_mask=0,
    **overrides,
):
    """Insert a sensor reading AND a corresponding bee_count."""
    rid = await _insert_reading(engine, hive_id, **overrides)
    async with AsyncSession(engine) as session:
        bc = BeeCount(
            reading_id=rid,
            hive_id=hive_id,
            observed_at=overrides.get("observed_at", utc_now()),
            ingested_at=overrides.get("ingested_at", utc_now()),
            period_ms=period_ms,
            bees_in=bees_in,
            bees_out=bees_out,
            lane_mask=lane_mask,
            stuck_mask=stuck_mask,
            sequence=overrides.get("sequence", 0),
            flags=overrides.get("flags", 0),
            sender_mac=overrides.get("sender_mac", "AA:BB:CC:DD:EE:FF"),
        )
        session.add(bc)
        await session.commit()
    return rid


# ---- POSSIBLE_SWARM (correlation) tests ----


async def test_possible_swarm_correlation_fires(engine, alert_engine, hive_with_reading):
    """Insert 30+ readings with weight drop >1.5kg AND bee_counts with net_out >500."""
    now = datetime.now(UTC)
    # 31 readings spread over the last hour
    # First 25 readings at high weight, last 6 at low weight (to create >1.5kg drop)
    # Each bee_count: bees_out=20, bees_in=1 => net_out=19 per reading
    # 31 * 19 = 589 > 500
    for i in range(31):
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 30)))
        weight = 35.0 if i < 25 else 33.0  # 2kg drop (>1.5kg threshold)
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=1,
            bees_out=20,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=weight,
        )

    # The trigger reading (last one in the window)
    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=1,
        bees_out=20,
        observed_at=observed,
        ingested_at=observed,
        sequence=100,
        weight_kg=33.0,
    )
    reading = {
        "weight_kg": 33.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    swarm_alerts = [a for a in alerts if a["type"] == "POSSIBLE_SWARM"]
    assert len(swarm_alerts) == 1
    assert swarm_alerts[0]["severity"] == "critical"


async def test_possible_swarm_no_fire_no_weight_drop(engine, alert_engine, hive_with_reading):
    """High net_out but no weight drop should not trigger POSSIBLE_SWARM."""
    now = datetime.now(UTC)
    for i in range(31):
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 30)))
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=1,
            bees_out=20,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=35.0,  # No weight change
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=1,
        bees_out=20,
        observed_at=observed,
        ingested_at=observed,
        sequence=100,
        weight_kg=35.0,
    )
    reading = {
        "weight_kg": 35.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "POSSIBLE_SWARM" for a in alerts)


async def test_possible_swarm_no_fire_insufficient_readings(
    engine, alert_engine, hive_with_reading
):
    """Less than 30 readings should not trigger correlation swarm."""
    now = datetime.now(UTC)
    for i in range(20):  # Only 20 readings, need >=30
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 19)))
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=1,
            bees_out=30,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=35.0 if i < 15 else 33.0,
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=1,
        bees_out=30,
        observed_at=observed,
        ingested_at=observed,
        sequence=100,
        weight_kg=33.0,
    )
    reading = {
        "weight_kg": 33.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "POSSIBLE_SWARM" for a in alerts)


async def test_possible_swarm_fallback_weight_only(engine, alert_engine, hive_with_reading):
    """No bee_counts rows means Phase 1 weight-only rule fires instead."""
    now = datetime.now(UTC)
    # Insert 6 readings (no bee_counts) with weight drop >2kg
    for i in range(6):
        ts = _ts(now - timedelta(minutes=50 - i * 10))
        weight = 35.0 if i < 5 else 32.0
        await _insert_reading(
            engine, 1, weight_kg=weight, observed_at=ts, ingested_at=ts, sequence=i
        )

    observed = _ts(now)
    await _insert_reading(
        engine, 1, weight_kg=32.0, observed_at=observed, ingested_at=observed, sequence=6
    )
    reading = {
        "weight_kg": 32.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    swarm_alerts = [a for a in alerts if a["type"] == "POSSIBLE_SWARM"]
    assert len(swarm_alerts) == 1
    assert swarm_alerts[0]["severity"] == "high"  # Phase 1 severity


# ---- ABSCONDING tests ----


async def test_absconding_fires(engine, alert_engine, hive_with_reading):
    """Weight drop >2kg AND net_out >400 over 2h with 60+ readings triggers ABSCONDING."""
    now = datetime.now(UTC)
    # 61 readings spread over 2 hours
    # net_out per reading: bees_out=10 - bees_in=3 = 7 => 61*7 = 427 > 400
    # Weight: first 50 at 35kg, last 11 at 32kg => drop 3kg > 2kg
    for i in range(61):
        ts = _ts(now - timedelta(minutes=115) + timedelta(minutes=i * (115 / 60)))
        weight = 35.0 if i < 50 else 32.0
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=3,
            bees_out=10,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=weight,
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=3,
        bees_out=10,
        observed_at=observed,
        ingested_at=observed,
        sequence=200,
        weight_kg=32.0,
    )
    reading = {
        "weight_kg": 32.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    absconding = [a for a in alerts if a["type"] == "ABSCONDING"]
    assert len(absconding) == 1
    assert absconding[0]["severity"] == "critical"


async def test_absconding_no_fire_short_window(engine, alert_engine, hive_with_reading):
    """Only 1h of data should not trigger ABSCONDING (needs 60+ readings in 2h)."""
    now = datetime.now(UTC)
    # 35 readings in 1 hour (not 60 in 2h)
    for i in range(35):
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 34)))
        weight = 35.0 if i < 25 else 32.0
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=3,
            bees_out=20,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=weight,
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=3,
        bees_out=20,
        observed_at=observed,
        ingested_at=observed,
        sequence=200,
        weight_kg=32.0,
    )
    reading = {
        "weight_kg": 32.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "ABSCONDING" for a in alerts)


# ---- ROBBING tests ----


async def test_robbing_fires(engine, alert_engine, hive_with_reading):
    """total_traffic >1000/hr AND net_out <-200 AND weight drop >0.5kg triggers ROBBING."""
    now = datetime.now(UTC)
    # 31 readings in 1 hour
    # bees_in=40, bees_out=5 per reading => net_out = 5-40 = -35 per reading
    # total_traffic = 45 per reading => 31*45 = 1395 > 1000
    # sum net_out = 31 * (-35) = -1085 < -200
    # weight: first 25 at 35kg, last 6 at 34kg => drop 1kg > 0.5kg
    for i in range(31):
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 30)))
        weight = 35.0 if i < 25 else 34.0
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=40,
            bees_out=5,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=weight,
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=40,
        bees_out=5,
        observed_at=observed,
        ingested_at=observed,
        sequence=100,
        weight_kg=34.0,
    )
    reading = {
        "weight_kg": 34.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    robbing = [a for a in alerts if a["type"] == "ROBBING"]
    assert len(robbing) == 1
    assert robbing[0]["severity"] == "high"


async def test_robbing_no_fire_no_weight_drop(engine, alert_engine, hive_with_reading):
    """Traffic conditions met but no weight drop should not trigger ROBBING."""
    now = datetime.now(UTC)
    for i in range(31):
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 30)))
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=40,
            bees_out=5,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=35.0,  # No weight change
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=40,
        bees_out=5,
        observed_at=observed,
        ingested_at=observed,
        sequence=100,
        weight_kg=35.0,
    )
    reading = {
        "weight_kg": 35.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "ROBBING" for a in alerts)


# ---- LOW_ACTIVITY tests ----


async def test_low_activity_fires(engine, alert_engine, hive_with_reading):
    """Today's traffic <20% of 7-day avg triggers LOW_ACTIVITY."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Insert 4 prior days with high traffic (10+ readings each, ~500 total_traffic/day)
    for day_offset in range(4, 0, -1):
        day_base = today_start - timedelta(days=day_offset)
        for j in range(15):  # 15 readings per day
            ts = _ts(day_base + timedelta(hours=j))
            # bees_in=20, bees_out=15 => total_traffic=35 per reading
            # 15 * 35 = 525 per day
            await _insert_reading_with_traffic(
                engine,
                1,
                bees_in=20,
                bees_out=15,
                observed_at=ts,
                ingested_at=ts,
                sequence=day_offset * 100 + j,
                weight_kg=30.0,
            )

    # Today: very low traffic (1 reading with total_traffic=2)
    ts_today = _ts(today_start + timedelta(hours=1))
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=1,
        bees_out=1,
        observed_at=ts_today,
        ingested_at=ts_today,
        sequence=999,
        weight_kg=30.0,
    )

    # Trigger reading
    observed = _ts(today_start + timedelta(hours=2))
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=0,
        bees_out=0,
        observed_at=observed,
        ingested_at=observed,
        sequence=1000,
        weight_kg=30.0,
    )
    reading = {
        "weight_kg": 30.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    low_act = [a for a in alerts if a["type"] == "LOW_ACTIVITY"]
    assert len(low_act) == 1
    assert low_act[0]["severity"] == "medium"


async def test_low_activity_no_fire_insufficient_history(engine, alert_engine, hive_with_reading):
    """Less than 3 prior days with data should not trigger LOW_ACTIVITY."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Only 2 prior days (need >= 3)
    for day_offset in range(2, 0, -1):
        day_base = today_start - timedelta(days=day_offset)
        for j in range(15):
            ts = _ts(day_base + timedelta(hours=j))
            await _insert_reading_with_traffic(
                engine,
                1,
                bees_in=20,
                bees_out=15,
                observed_at=ts,
                ingested_at=ts,
                sequence=day_offset * 100 + j,
                weight_kg=30.0,
            )

    # Today: low traffic
    ts_today = _ts(today_start + timedelta(hours=1))
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=1,
        bees_out=1,
        observed_at=ts_today,
        ingested_at=ts_today,
        sequence=999,
        weight_kg=30.0,
    )

    observed = _ts(today_start + timedelta(hours=2))
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=0,
        bees_out=0,
        observed_at=observed,
        ingested_at=observed,
        sequence=1000,
        weight_kg=30.0,
    )
    reading = {
        "weight_kg": 30.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0,
    }
    alerts = await alert_engine.check_reading(1, reading)
    assert not any(a["type"] == "LOW_ACTIVITY" for a in alerts)


# ---- Flag exclusion tests ----


async def test_first_boot_excluded(engine, alert_engine, hive_with_reading):
    """Readings with FIRST_BOOT flag (0x02) should be excluded from correlation."""
    now = datetime.now(UTC)
    # Insert 31 readings ALL with FIRST_BOOT flag
    for i in range(31):
        ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 30)))
        weight = 35.0 if i < 25 else 33.0
        await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=1,
            bees_out=20,
            observed_at=ts,
            ingested_at=ts,
            sequence=i,
            weight_kg=weight,
            flags=0x02,  # FIRST_BOOT
        )

    observed = _ts(now)
    await _insert_reading_with_traffic(
        engine,
        1,
        bees_in=1,
        bees_out=20,
        observed_at=observed,
        ingested_at=observed,
        sequence=100,
        weight_kg=33.0,
        flags=0x02,
    )
    reading = {
        "weight_kg": 33.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": observed,
        "flags": 0x02,
    }
    alerts = await alert_engine.check_reading(1, reading)
    # Correlation rules should not fire because all readings are excluded
    assert not any(a["type"] == "POSSIBLE_SWARM" and a["severity"] == "critical" for a in alerts)


# ---- Cooldown tests ----


async def test_cooldown_prevents_duplicate(engine, alert_engine, hive_with_reading):
    """Same correlation alert type should be suppressed within cooldown period."""
    now = datetime.now(UTC)

    async def _create_swarm_scenario(seq_base):
        """Insert readings that trigger correlation swarm."""
        for i in range(31):
            ts = _ts(now - timedelta(minutes=55) + timedelta(minutes=i * (55 / 30)))
            weight = 35.0 if i < 25 else 33.0
            await _insert_reading_with_traffic(
                engine,
                1,
                bees_in=1,
                bees_out=20,
                observed_at=ts,
                ingested_at=ts,
                sequence=seq_base + i,
                weight_kg=weight,
            )
        observed = _ts(now)
        rid = await _insert_reading_with_traffic(
            engine,
            1,
            bees_in=1,
            bees_out=20,
            observed_at=observed,
            ingested_at=observed,
            sequence=seq_base + 100,
            weight_kg=33.0,
        )
        return rid, observed

    # First swarm alert fires
    rid1, obs1 = await _create_swarm_scenario(0)
    reading1 = {
        "weight_kg": 33.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": obs1,
        "flags": 0,
    }
    alerts1 = await alert_engine.check_reading(1, reading1)
    assert any(a["type"] == "POSSIBLE_SWARM" for a in alerts1)

    # Second swarm alert should be suppressed by cooldown
    rid2, obs2 = await _create_swarm_scenario(500)
    reading2 = {
        "weight_kg": 33.0,
        "temp_c": 35.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1013.0,
        "battery_v": 3.7,
        "observed_at": obs2,
        "flags": 0,
    }
    alerts2 = await alert_engine.check_reading(1, reading2)
    assert not any(a["type"] == "POSSIBLE_SWARM" for a in alerts2)
