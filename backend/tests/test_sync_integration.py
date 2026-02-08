"""Cloud sync integration tests.

Tests the full sync cycle using mock Supabase client.
Mark with @pytest.mark.integration for tests requiring real Supabase.
"""

import copy
import hashlib
import os
import uuid

import bcrypt
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import Alert, CameraNode, Hive, Inspection, Photo
from waggle.services.sync import pull_alert_acks, pull_inspections, push_files, push_rows
from waggle.utils.timestamps import utc_now

# ---------------------------------------------------------------------------
# Mock Supabase client (adapted from test_cloud_sync.py)
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
    """Mock for supabase.table('name') — records upserts."""

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
    """Mock Supabase client for integration tests."""

    def __init__(self, fail_tables=None, pull_data=None):
        self.tables = {}
        self.rpc_calls = []
        self._fail_tables = fail_tables or []
        self._pull_data = pull_data or {}
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

# JPEG magic bytes (SOI marker)
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture
async def sync_env(tmp_path):
    """Set up a fresh database + photo directory with a seeded hive and camera node."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / ".waggle-sentinel").touch()

    key_hash = bcrypt.hashpw(b"k", bcrypt.gensalt(rounds=4)).decode()
    async with AsyncSession(engine) as session:
        async with session.begin():
            hive = Hive(id=1, name="Test Hive", created_at=utc_now())
            session.add(hive)
            await session.flush()
            node = CameraNode(
                device_id="cam-01",
                hive_id=1,
                api_key_hash=key_hash,
                created_at=utc_now(),
            )
            session.add(node)

    yield engine, str(photo_dir)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_full_push_pull_cycle(sync_env):
    """End-to-end test: push local rows, then pull a cloud-originated inspection.

    Steps:
    1. Seed a hive, alert, and inspection locally (all row_synced=0)
    2. Push rows to mock Supabase
    3. Verify all rows now row_synced=1
    4. Verify mock Supabase received the correct data in FK order
    5. Simulate a cloud-originated inspection arriving
    6. Pull inspections
    7. Verify the new inspection exists locally with source='cloud' and row_synced=1
    """
    engine, photo_dir = sync_env

    # -- Step 1: Seed alert and inspection (hive already seeded with row_synced=0) --
    now = utc_now()
    inspection_uuid = str(uuid.uuid4())

    async with AsyncSession(engine) as session:
        async with session.begin():
            alert = Alert(
                hive_id=1,
                type="HIGH_TEMP",
                severity="medium",
                message="Temperature above threshold",
                observed_at=now,
                acknowledged=0,
                created_at=now,
                updated_at=now,
                row_synced=0,
            )
            session.add(alert)

            inspection = Inspection(
                uuid=inspection_uuid,
                hive_id=1,
                inspected_at=now,
                queen_seen=0,
                notes="Local inspection",
                source="local",
                row_synced=0,
            )
            session.add(inspection)

    # -- Step 2: Push rows to mock Supabase --
    client = MockSupabaseClient()
    summary = await push_rows(engine, client)

    # -- Step 3: Verify all rows are now row_synced=1 --
    assert "hives" in summary
    assert "alerts" in summary
    assert "inspections" in summary
    # camera_nodes was seeded with default row_synced=0 too
    assert "camera_nodes" in summary

    async with AsyncSession(engine) as session:
        hive = (await session.execute(select(Hive).where(Hive.id == 1))).scalar_one()
        assert hive.row_synced == 1

        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].row_synced == 1

        insp = (await session.execute(select(Inspection))).scalar_one()
        assert insp.row_synced == 1

    # -- Step 4: Verify FK order of table access --
    # Hives must come before alerts and camera_nodes; inspections use RPC
    hive_idx = client.table_access_order.index("hives")
    alert_idx = client.table_access_order.index("alerts")
    cam_idx = client.table_access_order.index("camera_nodes")
    assert hive_idx < alert_idx
    assert hive_idx < cam_idx

    # Inspections should have used RPC, not table()
    assert any(call["fn"] == "upsert_inspection_lww" for call in client.rpc_calls)

    # -- Step 5: Simulate a cloud-originated inspection arriving --
    cloud_uuid = str(uuid.uuid4())
    cloud_time = "2099-01-01T00:00:00.000Z"
    cloud_inspections = [
        {
            "uuid": cloud_uuid,
            "hive_id": 1,
            "inspected_at": cloud_time,
            "created_at": cloud_time,
            "updated_at": cloud_time,
            "queen_seen": True,
            "brood_pattern": "good",
            "treatment_type": None,
            "treatment_notes": None,
            "notes": "Cloud inspection from mobile app",
            "source": "cloud",
        },
    ]

    # -- Step 6: Pull inspections --
    pull_client = MockSupabaseClient(pull_data={"inspections": cloud_inspections})
    count = await pull_inspections(engine, pull_client)
    assert count == 1

    # -- Step 7: Verify new inspection exists locally --
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Inspection).where(Inspection.uuid == cloud_uuid))
        cloud_insp = result.scalar_one()
        assert cloud_insp.source == "cloud"
        assert cloud_insp.row_synced == 1
        assert cloud_insp.notes == "Cloud inspection from mobile app"
        assert cloud_insp.queen_seen == 1  # True -> 1 in SQLite

        # Original local inspection should still exist
        result = await session.execute(
            select(Inspection).where(Inspection.uuid == inspection_uuid)
        )
        local_insp = result.scalar_one()
        assert local_insp.source == "local"
        assert local_insp.notes == "Local inspection"


async def test_bidirectional_inspection_sync(sync_env):
    """Conflict resolution: LWW ensures newer local data is not overwritten by older cloud data.

    Steps:
    1. Create local inspection (source='local', updated_at=T1)
    2. Push it to mock Supabase
    3. Simulate cloud update: same UUID, source='cloud', updated_at=T2 (T2 > T1)
    4. Pull inspections -> local inspection is updated with cloud data
    5. Create another local update (updated_at=T3 > T2)
    6. Pull inspections with old cloud data (T2)
    7. Verify local version is NOT overwritten (LWW)
    """
    engine, photo_dir = sync_env

    t1 = "2026-01-01T00:00:00.000Z"
    t2 = "2026-06-01T00:00:00.000Z"
    t3 = "2026-12-01T00:00:00.000Z"
    insp_uuid = str(uuid.uuid4())

    # -- Step 1: Create local inspection with updated_at=t1 --
    async with AsyncSession(engine) as session:
        async with session.begin():
            inspection = Inspection(
                uuid=insp_uuid,
                hive_id=1,
                inspected_at=t1,
                created_at=t1,
                updated_at=t1,
                queen_seen=0,
                notes="Original local notes",
                source="local",
                row_synced=0,
            )
            session.add(inspection)

    # -- Step 2: Push to mock Supabase --
    push_client = MockSupabaseClient()
    summary = await push_rows(engine, push_client)
    assert "inspections" in summary

    # Verify row_synced=1 after push
    async with AsyncSession(engine) as session:
        insp = (
            await session.execute(select(Inspection).where(Inspection.uuid == insp_uuid))
        ).scalar_one()
        assert insp.row_synced == 1

    # -- Step 3: Simulate cloud update (t2 > t1) --
    cloud_inspections_t2 = [
        {
            "uuid": insp_uuid,
            "hive_id": 1,
            "inspected_at": t2,
            "created_at": t1,
            "updated_at": t2,
            "queen_seen": True,
            "brood_pattern": "good",
            "treatment_type": "oxalic_acid",
            "treatment_notes": "Applied treatment",
            "notes": "Cloud updated notes",
            "source": "cloud",
        },
    ]

    # -- Step 4: Pull inspections -> local should be updated (cloud t2 > local t1) --
    pull_client = MockSupabaseClient(pull_data={"inspections": cloud_inspections_t2})
    count = await pull_inspections(engine, pull_client)
    assert count == 1

    async with AsyncSession(engine) as session:
        insp = (
            await session.execute(select(Inspection).where(Inspection.uuid == insp_uuid))
        ).scalar_one()
        assert insp.notes == "Cloud updated notes"
        assert insp.updated_at == t2
        assert insp.source == "cloud"
        assert insp.queen_seen == 1

    # -- Step 5: Simulate a local update (t3 > t2) --
    async with AsyncSession(engine) as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE inspections SET updated_at = :t3, notes = :notes, "
                    "source = 'local', row_synced = 0 WHERE uuid = :uuid"
                ),
                {"t3": t3, "notes": "Newer local notes", "uuid": insp_uuid},
            )

    # -- Step 6: Pull inspections with old cloud data (t2) --
    # We need to reset the watermark so the pull will re-process
    async with AsyncSession(engine) as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM sync_state WHERE key = 'pull_inspections_watermark'")
            )

    pull_client2 = MockSupabaseClient(pull_data={"inspections": cloud_inspections_t2})
    count = await pull_inspections(engine, pull_client2)

    # -- Step 7: Verify local version NOT overwritten (LWW: t3 > t2) --
    assert count == 0  # LWW should reject the older cloud data

    async with AsyncSession(engine) as session:
        insp = (
            await session.execute(select(Inspection).where(Inspection.uuid == insp_uuid))
        ).scalar_one()
        assert insp.notes == "Newer local notes"
        assert insp.updated_at == t3
        assert insp.source == "local"


async def test_alert_ack_round_trip(sync_env):
    """Alert acknowledgment sync: push unacked alert, then pull cloud ack.

    Steps:
    1. Create local alert (unacknowledged)
    2. Push to Supabase
    3. Simulate cloud acknowledgment
    4. Pull alert acks
    5. Verify local alert is now acknowledged
    """
    engine, photo_dir = sync_env

    now = utc_now()

    # -- Step 1: Create local alert (unacknowledged) --
    async with AsyncSession(engine) as session:
        async with session.begin():
            alert = Alert(
                hive_id=1,
                type="HIGH_TEMP",
                severity="medium",
                message="Temperature above threshold",
                observed_at=now,
                acknowledged=0,
                created_at=now,
                updated_at=now,
                row_synced=0,
            )
            session.add(alert)

    # Read back the alert to get the auto-generated id
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Alert))
        local_alert = result.scalar_one()
        alert_id = local_alert.id

    # -- Step 2: Push to mock Supabase --
    push_client = MockSupabaseClient()
    summary = await push_rows(engine, push_client)
    assert "alerts" in summary

    # Verify row_synced=1
    async with AsyncSession(engine) as session:
        alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one()
        assert alert.row_synced == 1
        assert alert.acknowledged == 0

    # -- Step 3: Simulate cloud acknowledgment --
    ack_time = "2099-01-01T00:00:00.000Z"
    cloud_alerts = [
        {
            "id": alert_id,
            "hive_id": 1,
            "type": "HIGH_TEMP",
            "severity": "medium",
            "message": "Temperature above threshold",
            "observed_at": now,
            "acknowledged": True,
            "acknowledged_at": ack_time,
            "acknowledged_by": "user@example.com",
            "updated_at": ack_time,
            "source": "cloud",
        },
    ]

    # -- Step 4: Pull alert acks --
    pull_client = MockSupabaseClient(pull_data={"alerts": cloud_alerts})
    count = await pull_alert_acks(engine, pull_client)
    assert count == 1

    # -- Step 5: Verify local alert is now acknowledged --
    async with AsyncSession(engine) as session:
        alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one()
        assert alert.acknowledged == 1
        assert alert.acknowledged_at == ack_time
        assert alert.acknowledged_by == "user@example.com"
        assert alert.row_synced == 1
        assert alert.updated_at == ack_time


async def test_photo_file_sync_e2e(sync_env):
    """Full photo pipeline: create photo with file, push to Supabase storage.

    Steps:
    1. Create hive + camera + photo (with actual file)
    2. Set ml_status='completed', file_synced=0
    3. Push files to mock Supabase storage
    4. Verify file was uploaded
    5. Verify file_synced=1 and supabase_path set
    """
    engine, photo_dir = sync_env

    # -- Step 1: Create a real photo file on disk --
    photo_path = "1/2026-01-01/cam-01_1_1.jpg"
    content, sha = _create_photo_file(photo_dir, photo_path)

    # -- Step 2: Create photo row with ml_status='completed', file_synced=0 --
    now = utc_now()
    async with AsyncSession(engine) as session:
        async with session.begin():
            photo = Photo(
                hive_id=1,
                device_id="cam-01",
                boot_id=1,
                captured_at=now,
                captured_at_source="device_ntp",
                sequence=1,
                photo_path=photo_path,
                file_size_bytes=len(content),
                sha256=sha,
                width=800,
                height=600,
                ml_status="completed",
                file_synced=0,
                row_synced=1,
            )
            session.add(photo)

    # -- Step 3: Push files to mock Supabase storage --
    client = MockSupabaseClient()
    count = await push_files(engine, client, photo_dir)

    # -- Step 4: Verify file was uploaded --
    assert count == 1
    bucket = client.storage.from_("photos")
    assert len(bucket.uploads) == 1
    assert bucket.uploads[0]["path"] == photo_path
    assert bucket.uploads[0]["data"] == content

    # -- Step 5: Verify file_synced=1 and supabase_path set in DB --
    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo))).scalar_one()
        assert photo.file_synced == 1
        assert photo.supabase_path == photo_path
