"""End-to-end integration tests: Phase 1 + Phase 2 pipeline coverage."""

import struct
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.config import Settings
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import Hive
from waggle.services.alert_engine import AlertEngine
from waggle.services.bridge import BridgeProcessor
from waggle.services.ingestion import IngestionService
from waggle.utils.cobs import cobs_encode
from waggle.utils.crc8 import crc8
from waggle.utils.timestamps import utc_now


def _build_test_payload(
    hive_id=1,
    sequence=42,
    weight_g=32120,
    temp_c_x100=3645,
    humidity_x100=5120,
    pressure_hpa_x10=10132,
    battery_mv=3710,
    flags=0,
) -> bytes:
    """Build a valid 32-byte Phase 1 payload with correct CRC."""
    data = struct.pack(
        "<BBHihHHHB",
        hive_id, 0x01, sequence,
        weight_g, temp_c_x100, humidity_x100,
        pressure_hpa_x10, battery_mv, flags,
    )
    crc_val = crc8(data[:17])
    return data + bytes([crc_val]) + bytes(14)  # 17 + 1 + 14 = 32


def _build_phase2_payload(
    hive_id=1,
    sequence=100,
    weight_g=30000,
    temp_c_x100=2500,
    humidity_x100=6000,
    pressure_hpa_x10=10100,
    battery_mv=3800,
    flags=0,
    bees_in=150,
    bees_out=120,
    period_ms=60000,
    lane_mask=0x0F,
    stuck_mask=0x00,
) -> bytes:
    """Build a valid 48-byte Phase 2 payload with correct CRC."""
    common = struct.pack(
        "<BBHihHHHB",
        hive_id, 0x02, sequence,
        weight_g, temp_c_x100, humidity_x100,
        pressure_hpa_x10, battery_mv, flags,
    )
    crc_val = crc8(common[:17])
    traffic = struct.pack("<HHIBB", bees_in, bees_out, period_ms, lane_mask, stuck_mask)
    return common + bytes([crc_val]) + traffic + bytes(20)  # 17 + 1 + 10 + 20 = 48


SENDER_MAC = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])


async def test_full_pipeline(tmp_path):
    """Phase 1: serial frame -> bridge decode -> worker ingest -> DB store -> API read."""
    # 1. Build payload and COBS-encoded frame
    payload = _build_test_payload(hive_id=1, weight_g=32120, temp_c_x100=3645)
    frame = SENDER_MAC + payload  # 6 + 32 = 38 bytes
    encoded_frame = cobs_encode(frame)

    # 2. Bridge: decode frame -> (topic, msg)
    bridge = BridgeProcessor()
    result = bridge.process_frame(encoded_frame)
    assert result is not None, "Bridge failed to decode valid frame"
    topic, msg = result
    assert topic == "waggle/1/sensors"
    assert msg["hive_id"] == 1
    assert msg["weight_g"] == 32120
    assert msg["temp_c_x100"] == 3645
    assert msg["sender_mac"] == "AA:BB:CC:DD:EE:FF"

    # 3. Set up DB
    db_path = tmp_path / "integration.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    # 4. Create hive matching the payload
    async with AsyncSession(engine) as session:
        hive = Hive(
            id=1,
            name="Test Hive",
            sender_mac="AA:BB:CC:DD:EE:FF",
            created_at=utc_now(),
        )
        session.add(hive)
        await session.commit()

    # 5. Ingest via worker service
    settings = Settings(API_KEY="test-key")
    alert_engine = AlertEngine(engine)
    ingestion = IngestionService(engine, settings, alert_engine)
    stored = await ingestion.process_message(topic, msg)
    assert stored is True, "Ingestion service rejected valid message"

    # 6. Query via API
    app = create_app(db_url=db_url, api_key="test-key")
    # Override the engine so the app uses our pre-populated DB
    app.state.engine = engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/hives/1/readings/latest",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"API returned {resp.status_code}: {resp.text}"
        reading = resp.json()

        # 7. Verify round-trip values (raw -> converted)
        # weight_g=32120 -> weight_kg=32.12
        assert reading["weight_kg"] == pytest.approx(32.12, abs=0.01)
        # temp_c_x100=3645 -> temp_c=36.45
        assert reading["temp_c"] == pytest.approx(36.45, abs=0.01)
        # humidity_x100=5120 -> humidity_pct=51.20
        assert reading["humidity_pct"] == pytest.approx(51.20, abs=0.01)
        # pressure_hpa_x10=10132 -> pressure_hpa=1013.2
        assert reading["pressure_hpa"] == pytest.approx(1013.2, abs=0.1)
        # battery_mv=3710 -> battery_v=3.71
        assert reading["battery_v"] == pytest.approx(3.71, abs=0.01)
        # Verify metadata fields
        assert reading["hive_id"] == 1
        assert reading["sequence"] == 42
        assert reading["flags"] == 0

    await engine.dispose()


async def test_phase2_pipeline(tmp_path):
    """Phase 2: 48-byte frame -> bridge decode -> worker ingest -> DB (sensor + bee_counts) -> API."""
    # 1. Build 48-byte payload and COBS-encode
    payload = _build_phase2_payload(
        hive_id=1, sequence=100,
        weight_g=30000, temp_c_x100=2500, humidity_x100=6000,
        pressure_hpa_x10=10100, battery_mv=3800, flags=0,
        bees_in=150, bees_out=120, period_ms=60000,
        lane_mask=0x0F, stuck_mask=0x00,
    )
    assert len(payload) == 48
    frame = SENDER_MAC + payload  # 6 + 48 = 54 bytes
    encoded_frame = cobs_encode(frame)

    # 2. Bridge: decode frame
    bridge = BridgeProcessor()
    result = bridge.process_frame(encoded_frame)
    assert result is not None, "Bridge failed to decode valid Phase 2 frame"
    topic, msg = result
    assert topic == "waggle/1/sensors"
    assert msg["msg_type"] == 2
    assert msg["hive_id"] == 1
    assert msg["weight_g"] == 30000
    assert msg["bees_in"] == 150
    assert msg["bees_out"] == 120
    assert msg["period_ms"] == 60000
    assert msg["lane_mask"] == 0x0F
    assert msg["stuck_mask"] == 0x00

    # 3. Set up DB
    db_path = tmp_path / "integration_p2.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    # 4. Create hive
    async with AsyncSession(engine) as session:
        hive = Hive(
            id=1,
            name="Test Hive",
            sender_mac="AA:BB:CC:DD:EE:FF",
            created_at=utc_now(),
        )
        session.add(hive)
        await session.commit()

    # 5. Ingest via worker
    settings = Settings(API_KEY="test-key")
    alert_engine = AlertEngine(engine)
    ingestion = IngestionService(engine, settings, alert_engine)
    stored = await ingestion.process_message(topic, msg)
    assert stored is True, "Ingestion rejected valid Phase 2 message"

    # 6. Verify via API
    app = create_app(db_url=db_url, api_key="test-key")
    app.state.engine = engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 6a. Verify sensor readings endpoint
        resp = await client.get(
            "/api/hives/1/readings/latest",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"Readings API returned {resp.status_code}: {resp.text}"
        reading = resp.json()
        assert reading["weight_kg"] == pytest.approx(30.0, abs=0.01)
        assert reading["temp_c"] == pytest.approx(25.0, abs=0.01)
        assert reading["humidity_pct"] == pytest.approx(60.0, abs=0.01)
        assert reading["pressure_hpa"] == pytest.approx(1010.0, abs=0.1)
        assert reading["battery_v"] == pytest.approx(3.8, abs=0.01)
        assert reading["hive_id"] == 1
        assert reading["sequence"] == 100

        # 6b. Verify traffic latest endpoint
        resp = await client.get(
            "/api/hives/1/traffic/latest",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"Traffic API returned {resp.status_code}: {resp.text}"
        traffic = resp.json()
        assert traffic["bees_in"] == 150
        assert traffic["bees_out"] == 120
        assert traffic["net_out"] == -30  # bees_out - bees_in = 120 - 150
        assert traffic["total_traffic"] == 270  # bees_in + bees_out
        assert traffic["period_ms"] == 60000
        assert traffic["lane_mask"] == 0x0F
        assert traffic["stuck_mask"] == 0x00
        assert traffic["hive_id"] == 1

    # 7. Direct DB verification of bee_counts table
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM bee_counts WHERE hive_id = 1")
        )
        assert result.scalar() == 1, "Expected exactly 1 row in bee_counts"

        result = await session.execute(
            text("SELECT bees_in, bees_out, net_out, total_traffic FROM bee_counts WHERE hive_id = 1")
        )
        row = result.first()
        assert row.bees_in == 150
        assert row.bees_out == 120
        assert row.net_out == -30
        assert row.total_traffic == 270

    await engine.dispose()


async def test_mixed_fleet(tmp_path):
    """Phase 1 + Phase 2 payloads coexist: sensor_readings has both, bee_counts only Phase 2."""
    # 1. Set up DB
    db_path = tmp_path / "integration_mixed.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    # 2. Create hive
    async with AsyncSession(engine) as session:
        hive = Hive(
            id=1,
            name="Mixed Fleet Hive",
            sender_mac="AA:BB:CC:DD:EE:FF",
            created_at=utc_now(),
        )
        session.add(hive)
        await session.commit()

    settings = Settings(API_KEY="test-key")
    alert_engine = AlertEngine(engine)
    ingestion = IngestionService(engine, settings, alert_engine)
    bridge = BridgeProcessor()

    # 3. Ingest Phase 1 payload (sequence=42)
    p1_payload = _build_test_payload(hive_id=1, sequence=42, weight_g=32120)
    p1_frame = SENDER_MAC + p1_payload
    p1_encoded = cobs_encode(p1_frame)
    topic1, msg1 = bridge.process_frame(p1_encoded)
    stored1 = await ingestion.process_message(topic1, msg1)
    assert stored1 is True, "Phase 1 message rejected"

    # 4. Ingest Phase 2 payload (sequence=100) — will have a later observed_at
    p2_payload = _build_phase2_payload(
        hive_id=1, sequence=100,
        weight_g=30000, temp_c_x100=2500, humidity_x100=6000,
        pressure_hpa_x10=10100, battery_mv=3800,
        bees_in=200, bees_out=180, period_ms=60000,
    )
    p2_frame = SENDER_MAC + p2_payload
    p2_encoded = cobs_encode(p2_frame)
    topic2, msg2 = bridge.process_frame(p2_encoded)
    stored2 = await ingestion.process_message(topic2, msg2)
    assert stored2 is True, "Phase 2 message rejected"

    # 5. Verify DB state
    async with AsyncSession(engine) as session:
        # sensor_readings should have 2 rows
        result = await session.execute(
            text("SELECT COUNT(*) FROM sensor_readings WHERE hive_id = 1")
        )
        assert result.scalar() == 2, "Expected 2 sensor_readings rows"

        # bee_counts should have 1 row (only Phase 2)
        result = await session.execute(
            text("SELECT COUNT(*) FROM bee_counts WHERE hive_id = 1")
        )
        assert result.scalar() == 1, "Expected 1 bee_counts row (Phase 2 only)"

    # 6. Verify API returns most recent reading (Phase 2, sequence=100)
    app = create_app(db_url=db_url, api_key="test-key")
    app.state.engine = engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Latest reading should be the Phase 2 one (later observed_at)
        resp = await client.get(
            "/api/hives/1/readings/latest",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        reading = resp.json()
        assert reading["sequence"] == 100, "Latest reading should be Phase 2 (seq=100)"
        assert reading["weight_kg"] == pytest.approx(30.0, abs=0.01)

        # Traffic latest should return Phase 2 data
        resp = await client.get(
            "/api/hives/1/traffic/latest",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        traffic = resp.json()
        assert traffic["bees_in"] == 200
        assert traffic["bees_out"] == 180
        assert traffic["net_out"] == -20  # 180 - 200
        assert traffic["total_traffic"] == 380  # 200 + 180

    await engine.dispose()


async def test_phase2_correlation_alert(tmp_path):
    """Verify POSSIBLE_SWARM correlation alert fires: weight drop >1.5kg AND net_out >500 in 1h."""
    # 1. Set up DB
    db_path = tmp_path / "integration_alert.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    # 2. Create hive
    async with AsyncSession(engine) as session:
        hive = Hive(
            id=1,
            name="Alert Test Hive",
            sender_mac="AA:BB:CC:DD:EE:FF",
            created_at=utc_now(),
        )
        session.add(hive)
        await session.commit()

    # 3. Insert 35 historical readings over the past ~55 minutes
    #    Weight starts at 32kg and drops to 30kg (2kg drop > 1.5kg threshold)
    #    Each reading also has bee_counts with high bees_out (net_out per reading ~20)
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        async with session.begin():
            for i in range(35):
                minutes_ago = 55 - i  # spread over 55 minutes, oldest first
                obs_time = now - timedelta(minutes=minutes_ago)
                obs_str = obs_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                ingested_str = obs_str

                # Weight drops linearly from 32.0 to 30.0 over 35 readings
                weight_kg = 32.0 - (2.0 * i / 34)

                await session.execute(
                    text(
                        "INSERT INTO sensor_readings "
                        "(hive_id, observed_at, ingested_at, weight_kg, temp_c, "
                        "humidity_pct, pressure_hpa, battery_v, sequence, flags, sender_mac) "
                        "VALUES (:hive_id, :observed_at, :ingested_at, :weight_kg, :temp_c, "
                        ":humidity_pct, :pressure_hpa, :battery_v, :sequence, :flags, :sender_mac)"
                    ),
                    {
                        "hive_id": 1,
                        "observed_at": obs_str,
                        "ingested_at": ingested_str,
                        "weight_kg": weight_kg,
                        "temp_c": 25.0,
                        "humidity_pct": 60.0,
                        "pressure_hpa": 1010.0,
                        "battery_v": 3.8,
                        "sequence": i,
                        "flags": 0,
                        "sender_mac": "AA:BB:CC:DD:EE:FF",
                    },
                )

                # Get the reading_id
                rid_result = await session.execute(text("SELECT last_insert_rowid()"))
                reading_id = rid_result.scalar()

                # Insert bee_counts with high bees_out (net_out >500 total: 35 * ~20 = 700)
                bees_out = 35
                bees_in = 15
                await session.execute(
                    text(
                        "INSERT INTO bee_counts "
                        "(reading_id, hive_id, observed_at, ingested_at, "
                        "period_ms, bees_in, bees_out, lane_mask, stuck_mask, "
                        "sequence, flags, sender_mac) "
                        "VALUES (:reading_id, :hive_id, :observed_at, :ingested_at, "
                        ":period_ms, :bees_in, :bees_out, :lane_mask, :stuck_mask, "
                        ":sequence, :flags, :sender_mac)"
                    ),
                    {
                        "reading_id": reading_id,
                        "hive_id": 1,
                        "observed_at": obs_str,
                        "ingested_at": ingested_str,
                        "period_ms": 60000,
                        "bees_in": bees_in,
                        "bees_out": bees_out,
                        "lane_mask": 0x0F,
                        "stuck_mask": 0x00,
                        "sequence": i,
                        "flags": 0,
                        "sender_mac": "AA:BB:CC:DD:EE:FF",
                    },
                )

    # 4. Now ingest one more Phase 2 payload via the full pipeline to trigger alert check.
    #    This payload continues the weight decline (30.0kg) with high bees_out.
    settings = Settings(API_KEY="test-key")
    alert_engine = AlertEngine(engine)
    ingestion = IngestionService(engine, settings, alert_engine)

    payload = _build_phase2_payload(
        hive_id=1, sequence=200,
        weight_g=30000, temp_c_x100=2500, humidity_x100=6000,
        pressure_hpa_x10=10100, battery_mv=3800, flags=0,
        bees_in=15, bees_out=35, period_ms=60000,
        lane_mask=0x0F, stuck_mask=0x00,
    )
    frame = SENDER_MAC + payload
    encoded_frame = cobs_encode(frame)

    bridge = BridgeProcessor()
    result = bridge.process_frame(encoded_frame)
    assert result is not None
    topic, msg = result
    stored = await ingestion.process_message(topic, msg)
    assert stored is True, "Trigger payload rejected"

    # 5. Verify that a POSSIBLE_SWARM alert was created
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text(
                "SELECT type, severity, message FROM alerts "
                "WHERE hive_id = 1 AND type = 'POSSIBLE_SWARM'"
            )
        )
        alert_row = result.first()
        assert alert_row is not None, "Expected POSSIBLE_SWARM alert to be created"
        assert alert_row.severity == "critical", (
            f"Correlation swarm should be critical, got {alert_row.severity}"
        )
        assert "Weight dropped" in alert_row.message
        assert "net_out" in alert_row.message

    # 6. Also verify via API
    app = create_app(db_url=db_url, api_key="test-key")
    app.state.engine = engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/alerts",
            headers={"X-API-Key": "test-key"},
            params={"hive_id": 1},
        )
        assert resp.status_code == 200
        alerts_data = resp.json()
        swarm_alerts = [
            a for a in alerts_data["items"]
            if a["type"] == "POSSIBLE_SWARM"
        ]
        assert len(swarm_alerts) >= 1, "Expected at least one POSSIBLE_SWARM alert via API"
        assert swarm_alerts[0]["severity"] == "critical"

    await engine.dispose()
