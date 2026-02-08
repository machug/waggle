"""Tests for cloud sync push service."""

import uuid

import bcrypt
import pytest
from sqlalchemy import select
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
)
from waggle.services.sync import PUSH_ORDER, push_rows
from waggle.utils.timestamps import utc_now

# ---------------------------------------------------------------------------
# Mock Supabase client
# ---------------------------------------------------------------------------


class MockSupabaseTable:
    """Mock for supabase.table('name')."""

    def __init__(self):
        self.upserted = []
        self._fail = False

    def upsert(self, rows):
        if self._fail:
            raise Exception("Network error")
        self.upserted.extend(rows if isinstance(rows, list) else [rows])
        return self

    def execute(self):
        return type("Response", (), {"data": self.upserted, "count": len(self.upserted)})()


class MockSupabaseClient:
    """Mock Supabase client for testing."""

    def __init__(self, fail_tables=None):
        self.tables = {}
        self.rpc_calls = []
        self._fail_tables = fail_tables or []
        # Track table access order for FK order test
        self.table_access_order = []

    def table(self, name):
        self.table_access_order.append(name)
        if name not in self.tables:
            self.tables[name] = MockSupabaseTable()
        if name in self._fail_tables:
            self.tables[name]._fail = True
        return self.tables[name]

    def rpc(self, fn_name, params):
        self.rpc_calls.append({"fn": fn_name, "params": params})
        return type("Response", (), {"data": None, "count": 0})()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sync_engine(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)
    yield engine
    await engine.dispose()


async def _seed_hive(engine, hive_id=1, synced=False):
    """Create a hive row. Returns the hive."""
    async with AsyncSession(engine) as session:
        async with session.begin():
            hive = Hive(
                id=hive_id,
                name=f"Hive {hive_id}",
                created_at=utc_now(),
                row_synced=1 if synced else 0,
            )
            session.add(hive)
    return hive


async def _seed_camera_node(engine, device_id="cam-01", hive_id=1, synced=False):
    """Create a camera node row."""
    key_hash = bcrypt.hashpw(b"test-key", bcrypt.gensalt(rounds=4)).decode()
    async with AsyncSession(engine) as session:
        async with session.begin():
            node = CameraNode(
                device_id=device_id,
                hive_id=hive_id,
                api_key_hash=key_hash,
                created_at=utc_now(),
                row_synced=1 if synced else 0,
            )
            session.add(node)
    return node


async def _seed_sensor_reading(engine, hive_id=1, synced=False):
    """Create a sensor reading row."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            reading = SensorReading(
                hive_id=hive_id,
                observed_at=now,
                ingested_at=now,
                weight_kg=30.0,
                temp_c=25.0,
                humidity_pct=60.0,
                battery_v=3.7,
                sequence=1,
                flags=0,
                sender_mac="AA:BB:CC:DD:EE:01",
                row_synced=1 if synced else 0,
            )
            session.add(reading)
    return reading


async def _seed_bee_count(engine, reading_id=1, hive_id=1, synced=False):
    """Create a bee count row."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            bc = BeeCount(
                reading_id=reading_id,
                hive_id=hive_id,
                observed_at=now,
                period_ms=30000,
                bees_in=10,
                bees_out=5,
                lane_mask=0xFF,
                stuck_mask=0x00,
                sequence=1,
                flags=0,
                sender_mac="AA:BB:CC:DD:EE:01",
                row_synced=1 if synced else 0,
            )
            session.add(bc)
    return bc


async def _seed_photo(engine, hive_id=1, device_id="cam-01", synced=False):
    """Create a photo row."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            photo = Photo(
                hive_id=hive_id,
                device_id=device_id,
                boot_id=1,
                captured_at=now,
                captured_at_source="device_ntp",
                sequence=1,
                photo_path="1/2026-01-01/cam-01_1_1.jpg",
                file_size_bytes=1024,
                sha256="a" * 64,
                width=800,
                height=600,
                row_synced=1 if synced else 0,
            )
            session.add(photo)
    return photo


async def _seed_ml_detection(engine, photo_id=1, hive_id=1, synced=False):
    """Create an ML detection row."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            det = MlDetection(
                photo_id=photo_id,
                hive_id=hive_id,
                detected_at=now,
                top_class="bee",
                top_confidence=0.95,
                detections_json="[]",
                inference_ms=50,
                model_hash="hash123",
                row_synced=1 if synced else 0,
            )
            session.add(det)
    return det


async def _seed_alert(engine, hive_id=1, acknowledged=0, synced=False):
    """Create an alert row."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            alert = Alert(
                hive_id=hive_id,
                type="HIGH_TEMP",
                severity="medium",
                message="Temperature above threshold",
                observed_at=now,
                acknowledged=acknowledged,
                created_at=now,
                updated_at=now,
                row_synced=1 if synced else 0,
            )
            session.add(alert)
    return alert


async def _seed_inspection(engine, hive_id=1, queen_seen=0, synced=False):
    """Create an inspection row."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            inspection = Inspection(
                uuid=str(uuid.uuid4()),
                hive_id=hive_id,
                inspected_at=now,
                queen_seen=queen_seen,
                notes="Test inspection",
                row_synced=1 if synced else 0,
            )
            session.add(inspection)
    return inspection


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_push_marks_rows_synced(sync_engine):
    """Create unsynced hive + sensor_reading, push, verify row_synced=1 after push."""
    await _seed_hive(sync_engine)
    await _seed_sensor_reading(sync_engine)

    client = MockSupabaseClient()
    summary = await push_rows(sync_engine, client)

    assert summary["hives"] == 1
    assert summary["sensor_readings"] == 1

    # Verify row_synced = 1 in DB
    async with AsyncSession(sync_engine) as session:
        hive = (await session.execute(select(Hive).where(Hive.id == 1))).scalar_one()
        assert hive.row_synced == 1

        readings = (await session.execute(select(SensorReading))).scalars().all()
        assert len(readings) == 1
        assert readings[0].row_synced == 1


async def test_push_respects_fk_order(sync_engine):
    """Create unsynced data in all tables, push, verify FK order is respected."""
    # Seed all tables in dependency order
    await _seed_hive(sync_engine)
    await _seed_camera_node(sync_engine)
    await _seed_sensor_reading(sync_engine)
    await _seed_bee_count(sync_engine)
    await _seed_photo(sync_engine)
    await _seed_ml_detection(sync_engine)
    await _seed_alert(sync_engine)
    await _seed_inspection(sync_engine)

    client = MockSupabaseClient()
    summary = await push_rows(sync_engine, client)

    # All tables should have been pushed
    assert len(summary) == 8

    # Verify table access order matches PUSH_ORDER (inspections use rpc, not table())
    expected_table_order = [name for name, _ in PUSH_ORDER if name != "inspections"]
    assert client.table_access_order == expected_table_order

    # Verify inspections used RPC
    assert len(client.rpc_calls) == 1
    assert client.rpc_calls[0]["fn"] == "upsert_inspection_lww"


async def test_push_handles_network_error(sync_engine):
    """Make one table fail, verify that table's rows stay row_synced=0 while others succeed."""
    await _seed_hive(sync_engine)
    await _seed_sensor_reading(sync_engine)

    # Fail sensor_readings push but let hives succeed
    client = MockSupabaseClient(fail_tables=["sensor_readings"])
    summary = await push_rows(sync_engine, client)

    # Hives should succeed
    assert summary.get("hives") == 1

    # sensor_readings should NOT be in summary (failed)
    assert "sensor_readings" not in summary

    # Verify hive is synced but reading is not
    async with AsyncSession(sync_engine) as session:
        hive = (await session.execute(select(Hive).where(Hive.id == 1))).scalar_one()
        assert hive.row_synced == 1

        reading = (await session.execute(select(SensorReading))).scalar_one()
        assert reading.row_synced == 0


async def test_push_skips_synced_rows(sync_engine):
    """Create rows with row_synced=1, push, verify they're NOT pushed to Supabase."""
    await _seed_hive(sync_engine, synced=True)
    await _seed_sensor_reading(sync_engine, synced=True)

    client = MockSupabaseClient()
    summary = await push_rows(sync_engine, client)

    # Nothing should have been pushed
    assert summary == {}
    assert len(client.tables) == 0
    assert len(client.rpc_calls) == 0


async def test_inspection_push_uses_rpc(sync_engine):
    """Create unsynced inspection, push, verify supabase_client.rpc was called."""
    await _seed_hive(sync_engine, synced=True)  # Hive already synced
    await _seed_inspection(sync_engine)

    client = MockSupabaseClient()
    summary = await push_rows(sync_engine, client)

    assert summary["inspections"] == 1
    assert len(client.rpc_calls) == 1
    assert client.rpc_calls[0]["fn"] == "upsert_inspection_lww"
    # Verify the params contain the inspection data
    params = client.rpc_calls[0]["params"]
    assert "uuid" in params
    assert "hive_id" in params
    assert params["hive_id"] == 1


async def test_push_boolean_conversion(sync_engine):
    """Alert with acknowledged=1 should produce acknowledged=True in Supabase dict."""
    await _seed_hive(sync_engine, synced=True)  # Hive already synced
    await _seed_alert(sync_engine, acknowledged=1)

    client = MockSupabaseClient()
    summary = await push_rows(sync_engine, client)

    assert summary["alerts"] == 1

    # Check what was upserted to Supabase
    alert_table = client.tables["alerts"]
    assert len(alert_table.upserted) == 1
    upserted_alert = alert_table.upserted[0]
    assert upserted_alert["acknowledged"] is True
    # Verify row_synced and file_synced are NOT in the dict
    assert "row_synced" not in upserted_alert
