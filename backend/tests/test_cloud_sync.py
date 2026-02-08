"""Tests for cloud sync push and pull service."""

import copy
import hashlib
import os
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
    SyncState,
)
from waggle.services.sync import (
    PUSH_ORDER,
    pull_alert_acks,
    pull_inspections,
    push_files,
    push_rows,
    run_sync,
)
from waggle.utils.timestamps import utc_now

# ---------------------------------------------------------------------------
# Mock Supabase client
# ---------------------------------------------------------------------------


class MockQueryBuilder:
    """Mock for Supabase table query builder pattern."""

    def __init__(self, data=None, fail=False):
        self._data = copy.deepcopy(data) if data else []
        self._fail = fail

    def select(self, *args):
        return self

    def eq(self, col, val):
        self._data = [r for r in self._data if r.get(col) == val]
        return self

    def gte(self, col, val):
        self._data = [r for r in self._data if r.get(col, "") >= val]
        return self

    def order(self, col, desc=False):
        self._data.sort(key=lambda r: r.get(col, ""), reverse=desc)
        return self

    def limit(self, n):
        self._data = self._data[:n]
        return self

    def execute(self):
        if self._fail:
            raise Exception("Network error")
        return type("Response", (), {"data": self._data})()


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


class MockStorageBucket:
    def __init__(self, fail=False):
        self.uploads = []
        self._fail = fail

    def upload(self, path, data, file_options=None):
        if self._fail:
            raise Exception("Storage upload error")
        self.uploads.append({"path": path, "data": data, "options": file_options})
        return {"Key": path}


class MockStorage:
    def __init__(self, fail=False):
        self.buckets = {}
        self._fail = fail

    def from_(self, bucket_name):
        if bucket_name not in self.buckets:
            self.buckets[bucket_name] = MockStorageBucket(fail=self._fail)
        return self.buckets[bucket_name]


class MockSupabaseClient:
    """Mock Supabase client for testing."""

    def __init__(self, fail_tables=None, pull_data=None):
        self.tables = {}
        self.rpc_calls = []
        self._fail_tables = fail_tables or []
        self._pull_data = pull_data or {}
        # Track table access order for FK order test
        self.table_access_order = []
        self.storage = MockStorage()

    def table(self, name):
        self.table_access_order.append(name)
        # If pull_data is configured for this table, return a query builder
        if name in self._pull_data:
            fail = name in self._fail_tables
            return MockQueryBuilder(data=self._pull_data[name], fail=fail)
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


# ---------------------------------------------------------------------------
# Helpers for file sync tests
# ---------------------------------------------------------------------------

# JPEG magic bytes (SOI marker)
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _create_photo_file(photo_dir, relative_path, content=None):
    """Create a photo file on disk and return (content, sha256)."""
    if content is None:
        content = JPEG_MAGIC
    full_path = os.path.join(photo_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)
    sha = hashlib.sha256(content).hexdigest()
    return content, sha


async def _seed_photo_for_file_sync(
    engine,
    hive_id=1,
    device_id="cam-01",
    ml_status="completed",
    file_synced=0,
    sha256="a" * 64,
    photo_path="1/2026-01-01/cam-01_1_1.jpg",
):
    """Create a photo row configured for file sync tests."""
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
                photo_path=photo_path,
                file_size_bytes=len(JPEG_MAGIC),
                sha256=sha256,
                width=800,
                height=600,
                ml_status=ml_status,
                file_synced=file_synced,
                row_synced=1,
            )
            session.add(photo)
    return photo


# ---------------------------------------------------------------------------
# File sync tests
# ---------------------------------------------------------------------------


async def test_push_files_uploads_to_storage(sync_engine, tmp_path):
    """Create photo with file_synced=0, ml_status='completed', push, verify upload."""
    photo_dir = str(tmp_path / "photos")
    os.makedirs(photo_dir, exist_ok=True)
    # Create sentinel
    with open(os.path.join(photo_dir, ".waggle-sentinel"), "w") as f:
        f.write("")

    photo_path = "1/2026-01-01/cam-01_1_1.jpg"
    content, sha = _create_photo_file(photo_dir, photo_path)

    # Seed DB prerequisites
    await _seed_hive(sync_engine, synced=True)
    await _seed_camera_node(sync_engine, synced=True)
    await _seed_photo_for_file_sync(sync_engine, sha256=sha)

    client = MockSupabaseClient()
    count = await push_files(sync_engine, client, photo_dir)

    assert count == 1

    # Verify upload happened
    bucket = client.storage.from_("photos")
    assert len(bucket.uploads) == 1
    assert bucket.uploads[0]["path"] == photo_path
    assert bucket.uploads[0]["data"] == content

    # Verify file_synced = 1 in DB
    async with AsyncSession(sync_engine) as session:
        photo = (await session.execute(select(Photo))).scalar_one()
        assert photo.file_synced == 1


async def test_push_files_verifies_sha256(sync_engine, tmp_path):
    """Create photo with wrong sha256, push, verify NOT uploaded."""
    photo_dir = str(tmp_path / "photos")
    os.makedirs(photo_dir, exist_ok=True)
    with open(os.path.join(photo_dir, ".waggle-sentinel"), "w") as f:
        f.write("")

    photo_path = "1/2026-01-01/cam-01_1_1.jpg"
    _create_photo_file(photo_dir, photo_path)

    await _seed_hive(sync_engine, synced=True)
    await _seed_camera_node(sync_engine, synced=True)
    # Use a wrong sha256 hash
    await _seed_photo_for_file_sync(sync_engine, sha256="bad_hash_" + "0" * 55)

    client = MockSupabaseClient()
    count = await push_files(sync_engine, client, photo_dir)

    assert count == 0
    # No uploads should have occurred
    assert "photos" not in client.storage.buckets

    # file_synced should still be 0
    async with AsyncSession(sync_engine) as session:
        photo = (await session.execute(select(Photo))).scalar_one()
        assert photo.file_synced == 0


async def test_push_files_skips_pending_ml(sync_engine, tmp_path):
    """Photo with ml_status='pending' should NOT be uploaded."""
    photo_dir = str(tmp_path / "photos")
    os.makedirs(photo_dir, exist_ok=True)
    with open(os.path.join(photo_dir, ".waggle-sentinel"), "w") as f:
        f.write("")

    photo_path = "1/2026-01-01/cam-01_1_1.jpg"
    content, sha = _create_photo_file(photo_dir, photo_path)

    await _seed_hive(sync_engine, synced=True)
    await _seed_camera_node(sync_engine, synced=True)
    await _seed_photo_for_file_sync(sync_engine, sha256=sha, ml_status="pending")

    client = MockSupabaseClient()
    count = await push_files(sync_engine, client, photo_dir)

    assert count == 0
    assert "photos" not in client.storage.buckets


async def test_push_files_sets_supabase_path(sync_engine, tmp_path):
    """After successful upload, supabase_path column should be set."""
    photo_dir = str(tmp_path / "photos")
    os.makedirs(photo_dir, exist_ok=True)
    with open(os.path.join(photo_dir, ".waggle-sentinel"), "w") as f:
        f.write("")

    photo_path = "1/2026-01-01/cam-01_1_1.jpg"
    content, sha = _create_photo_file(photo_dir, photo_path)

    await _seed_hive(sync_engine, synced=True)
    await _seed_camera_node(sync_engine, synced=True)
    await _seed_photo_for_file_sync(sync_engine, sha256=sha)

    client = MockSupabaseClient()
    await push_files(sync_engine, client, photo_dir)

    async with AsyncSession(sync_engine) as session:
        photo = (await session.execute(select(Photo))).scalar_one()
        assert photo.supabase_path == photo_path
        assert photo.file_synced == 1


async def test_push_files_sentinel_guard(sync_engine, tmp_path):
    """No sentinel file should return 0 immediately."""
    photo_dir = str(tmp_path / "photos")
    os.makedirs(photo_dir, exist_ok=True)
    # No sentinel file created

    client = MockSupabaseClient()
    count = await push_files(sync_engine, client, photo_dir)

    assert count == 0


# ---------------------------------------------------------------------------
# Pull sync tests
# ---------------------------------------------------------------------------


async def test_pull_inspections_creates_local_rows(sync_engine):
    """Mock Supabase returns 2 inspections with source='cloud', pull creates them locally."""
    await _seed_hive(sync_engine, synced=True)

    uuid1 = str(uuid.uuid4())
    uuid2 = str(uuid.uuid4())
    now = utc_now()

    cloud_inspections = [
        {
            "uuid": uuid1,
            "hive_id": 1,
            "inspected_at": now,
            "created_at": now,
            "updated_at": now,
            "queen_seen": True,
            "brood_pattern": "good",
            "treatment_type": None,
            "treatment_notes": None,
            "notes": "Cloud inspection 1",
            "source": "cloud",
        },
        {
            "uuid": uuid2,
            "hive_id": 1,
            "inspected_at": now,
            "created_at": now,
            "updated_at": now,
            "queen_seen": False,
            "brood_pattern": None,
            "treatment_type": None,
            "treatment_notes": None,
            "notes": "Cloud inspection 2",
            "source": "cloud",
        },
    ]

    client = MockSupabaseClient(pull_data={"inspections": cloud_inspections})
    count = await pull_inspections(sync_engine, client)

    assert count == 2

    # Verify rows exist in local DB
    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Inspection).order_by(Inspection.uuid))
        inspections = result.scalars().all()
        assert len(inspections) == 2

        uuids = {i.uuid for i in inspections}
        assert uuid1 in uuids
        assert uuid2 in uuids

        # All should be marked as synced
        for insp in inspections:
            assert insp.row_synced == 1
            assert insp.source == "cloud"


async def test_pull_inspections_lww(sync_engine):
    """Local inspection with newer updated_at is NOT overwritten by cloud version."""
    await _seed_hive(sync_engine, synced=True)

    test_uuid = str(uuid.uuid4())
    old_time = "2026-01-01T00:00:00.000Z"
    new_time = "2026-02-01T00:00:00.000Z"

    # Create a local inspection with newer updated_at
    async with AsyncSession(sync_engine) as session:
        async with session.begin():
            inspection = Inspection(
                uuid=test_uuid,
                hive_id=1,
                inspected_at=new_time,
                created_at=old_time,
                updated_at=new_time,
                queen_seen=1,
                notes="Local version - newer",
                source="local",
                row_synced=1,
            )
            session.add(inspection)

    # Cloud has older version
    cloud_inspections = [
        {
            "uuid": test_uuid,
            "hive_id": 1,
            "inspected_at": old_time,
            "created_at": old_time,
            "updated_at": old_time,
            "queen_seen": False,
            "brood_pattern": None,
            "treatment_type": None,
            "treatment_notes": None,
            "notes": "Cloud version - older",
            "source": "cloud",
        },
    ]

    client = MockSupabaseClient(pull_data={"inspections": cloud_inspections})
    count = await pull_inspections(sync_engine, client)

    # Should NOT have been updated (LWW: local is newer)
    assert count == 0

    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Inspection).where(Inspection.uuid == test_uuid))
        insp = result.scalar_one()
        assert insp.notes == "Local version - newer"
        assert insp.updated_at == new_time


async def test_pull_inspections_updates_watermark(sync_engine):
    """After pulling, sync_state contains the watermark."""
    await _seed_hive(sync_engine, synced=True)

    test_uuid = str(uuid.uuid4())
    now = "2026-02-01T12:00:00.000Z"

    cloud_inspections = [
        {
            "uuid": test_uuid,
            "hive_id": 1,
            "inspected_at": now,
            "created_at": now,
            "updated_at": now,
            "queen_seen": False,
            "brood_pattern": None,
            "treatment_type": None,
            "treatment_notes": None,
            "notes": "Test",
            "source": "cloud",
        },
    ]

    client = MockSupabaseClient(pull_data={"inspections": cloud_inspections})
    await pull_inspections(sync_engine, client)

    # Check watermark in sync_state
    async with AsyncSession(sync_engine) as session:
        result = await session.execute(
            select(SyncState.value).where(SyncState.key == "pull_inspections_watermark")
        )
        watermark = result.scalar_one()
        assert watermark == f"{now}|{test_uuid}"


async def test_pull_alert_acks_updates_local(sync_engine):
    """Cloud alert with acknowledged=true updates local alert."""
    await _seed_hive(sync_engine, synced=True)
    await _seed_alert(sync_engine, acknowledged=0, synced=True)

    # Read back the alert to get the id and updated_at
    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Alert))
        local_alert = result.scalar_one()
        alert_id = local_alert.id
        local_updated_at = local_alert.updated_at

    # Cloud has a newer ack
    newer_time = "2099-01-01T00:00:00.000Z"
    cloud_alerts = [
        {
            "id": alert_id,
            "hive_id": 1,
            "type": "HIGH_TEMP",
            "severity": "medium",
            "message": "Temperature above threshold",
            "observed_at": local_updated_at,
            "acknowledged": True,
            "acknowledged_at": newer_time,
            "acknowledged_by": "cloud_user",
            "updated_at": newer_time,
            "source": "cloud",
        },
    ]

    client = MockSupabaseClient(pull_data={"alerts": cloud_alerts})
    count = await pull_alert_acks(sync_engine, client)

    assert count == 1

    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Alert).where(Alert.id == alert_id))
        updated_alert = result.scalar_one()
        assert updated_alert.acknowledged == 1
        assert updated_alert.acknowledged_at == newer_time
        assert updated_alert.acknowledged_by == "cloud_user"
        assert updated_alert.row_synced == 1


async def test_pull_alert_acks_lww(sync_engine):
    """Local alert with newer updated_at is NOT overwritten."""
    await _seed_hive(sync_engine, synced=True)

    # Create alert with a very new updated_at
    newer_time = "2099-01-01T00:00:00.000Z"
    async with AsyncSession(sync_engine) as session:
        async with session.begin():
            alert = Alert(
                hive_id=1,
                type="HIGH_TEMP",
                severity="medium",
                message="Temperature above threshold",
                observed_at=newer_time,
                acknowledged=0,
                created_at=newer_time,
                updated_at=newer_time,
                row_synced=1,
            )
            session.add(alert)

    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Alert))
        local_alert = result.scalar_one()
        alert_id = local_alert.id

    # Cloud has an older version
    older_time = "2026-01-01T00:00:00.000Z"
    cloud_alerts = [
        {
            "id": alert_id,
            "hive_id": 1,
            "type": "HIGH_TEMP",
            "severity": "medium",
            "message": "Temperature above threshold",
            "observed_at": older_time,
            "acknowledged": True,
            "acknowledged_at": older_time,
            "acknowledged_by": "old_user",
            "updated_at": older_time,
            "source": "cloud",
        },
    ]

    client = MockSupabaseClient(pull_data={"alerts": cloud_alerts})
    count = await pull_alert_acks(sync_engine, client)

    # Should NOT have updated (LWW: local is newer)
    assert count == 0

    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one()
        assert alert.acknowledged == 0
        assert alert.updated_at == newer_time


async def test_pull_handles_network_error(sync_engine):
    """Mock Supabase raises exception, returns 0, no local changes."""
    await _seed_hive(sync_engine, synced=True)

    # fail_tables causes MockQueryBuilder to raise on execute()
    cloud_data = [
        {
            "uuid": "x",
            "source": "cloud",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    client = MockSupabaseClient(
        pull_data={"inspections": cloud_data},
        fail_tables=["inspections"],
    )
    count = await pull_inspections(sync_engine, client)

    assert count == 0

    # No inspections should exist locally
    async with AsyncSession(sync_engine) as session:
        result = await session.execute(select(Inspection))
        assert result.scalars().all() == []

    # No watermark should exist
    async with AsyncSession(sync_engine) as session:
        result = await session.execute(
            select(SyncState.value).where(SyncState.key == "pull_inspections_watermark")
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Main loop tests
# ---------------------------------------------------------------------------


async def test_run_sync_single_iteration(tmp_path):
    """Run with max_iterations=1, verify all 4 sync operations are called."""
    from unittest.mock import AsyncMock, MagicMock, patch

    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    photo_dir = str(tmp_path / "photos")
    os.makedirs(photo_dir, exist_ok=True)

    mock_push_rows = AsyncMock(return_value={"hives": 1})
    mock_push_files = AsyncMock(return_value=2)
    mock_pull_inspections = AsyncMock(return_value=3)
    mock_pull_alert_acks = AsyncMock(return_value=1)

    mock_create_client = MagicMock(return_value=MagicMock())

    with (
        patch("waggle.services.sync.push_rows", mock_push_rows),
        patch("waggle.services.sync.push_files", mock_push_files),
        patch("waggle.services.sync.pull_inspections", mock_pull_inspections),
        patch("waggle.services.sync.pull_alert_acks", mock_pull_alert_acks),
        patch("supabase.create_client", mock_create_client),
    ):
        await run_sync(
            db_url=db_url,
            photo_dir=photo_dir,
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
            interval_sec=1,
            max_iterations=1,
        )

    mock_push_rows.assert_called_once()
    mock_push_files.assert_called_once()
    mock_pull_inspections.assert_called_once()
    mock_pull_alert_acks.assert_called_once()
    mock_create_client.assert_called_once_with("https://fake.supabase.co", "fake-key")
