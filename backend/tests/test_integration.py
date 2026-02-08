"""End-to-end integration test: serial frame -> bridge -> worker -> DB -> API."""

import struct

import pytest
from httpx import ASGITransport, AsyncClient
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
    """Build a valid 32-byte payload with correct CRC."""
    data = struct.pack(
        "<BBHihHHHB",
        hive_id, 0x01, sequence,
        weight_g, temp_c_x100, humidity_x100,
        pressure_hpa_x10, battery_mv, flags,
    )
    crc_val = crc8(data[:17])
    return data + bytes([crc_val]) + bytes(14)  # 17 + 1 + 14 = 32


SENDER_MAC = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])


async def test_full_pipeline(tmp_path):
    """Simulate: serial frame -> bridge decode -> worker ingest -> DB store -> API read."""
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
