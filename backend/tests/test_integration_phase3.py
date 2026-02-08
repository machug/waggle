"""End-to-end integration tests: Phase 3 vision + ML pipeline coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import Alert, Hive
from waggle.services.alert_engine import AlertEngine
from waggle.services.ml_worker import process_one
from waggle.services.notify import dispatch_webhooks
from waggle.services.photo_pruning import prune_photos
from waggle.utils.timestamps import utc_now

# ---------------------------------------------------------------------------
# Mock YOLO model objects (same pattern as test_ml_worker.py)
# ---------------------------------------------------------------------------


class MockBoxes:
    def __init__(self, detections):
        self._dets = detections

    @property
    def cls(self):
        return [d["cls_id"] for d in self._dets]

    @property
    def conf(self):
        return [d["conf"] for d in self._dets]

    @property
    def xyxy(self):
        return [d["bbox"] for d in self._dets]


class MockResult:
    def __init__(self, detections):
        self.boxes = MockBoxes(detections)


class MockYolo:
    def __init__(self, detections=None):
        self.detections = detections or []
        self.names = {0: "bee", 1: "varroa", 2: "pollen", 3: "wasp"}
        self.model_hash = "mock-hash"

    def __call__(self, path, verbose=False):
        return [MockResult(self.detections)]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# A 32-byte bcrypt-compatible API key
RAW_CAMERA_KEY = "a" * 32


class FakeSettings:
    """Minimal settings object for create_app."""

    def __init__(self, photo_dir: str):
        self.PHOTO_DIR = photo_dir
        self.MAX_PHOTO_SIZE = 204800
        self.MAX_QUEUE_DEPTH = 50
        self.DISK_USAGE_THRESHOLD = 0.90
        self.FASTAPI_BASE_URL = "http://test"
        self.LOCAL_SIGNING_SECRET = "test-secret"
        self.LOCAL_SIGNING_TTL_SEC = 600


def _make_jpeg(size: int = 200) -> bytes:
    """Build a minimal valid JPEG (starts with FF D8 FF magic bytes)."""
    return b"\xff\xd8\xff" + b"\x00" * (size - 3)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def integration_app(tmp_path):
    """Full Phase 3 app with photo storage, returns (app, engine, photo_dir)."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / ".waggle-sentinel").touch()

    settings = FakeSettings(str(photo_dir))

    app = create_app(
        db_url=db_url,
        api_key="test-key",
        admin_api_key="admin-key",
        settings=settings,
    )

    engine = create_engine_from_url(db_url)
    await init_db(engine)

    # Point the app at our pre-populated engine
    app.state.engine = engine

    yield app, engine, str(photo_dir)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test 1: Full Photo Pipeline
# ---------------------------------------------------------------------------


async def test_full_photo_pipeline(integration_app):
    """Register camera -> upload JPEG -> ML processes -> detection stored -> alert fires."""
    app, engine, photo_dir = integration_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create hive
        resp = await client.post(
            "/api/hives",
            json={"id": 1, "name": "Photo Test Hive"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201, f"Create hive failed: {resp.text}"

        # 2. Register camera node (admin endpoint)
        resp = await client.post(
            "/api/admin/camera-nodes",
            json={
                "device_id": "cam-01",
                "hive_id": 1,
                "api_key": RAW_CAMERA_KEY,
            },
            headers={"X-Admin-Key": "admin-key"},
        )
        assert resp.status_code == 201, f"Register camera failed: {resp.text}"

        # 3. Upload a JPEG via device auth
        jpeg_data = _make_jpeg(500)
        resp = await client.post(
            "/api/photos/upload",
            files={"photo": ("test.jpg", jpeg_data, "image/jpeg")},
            data={
                "hive_id": "1",
                "sequence": "0",
                "boot_id": "1",
                "captured_at": utc_now(),
                "captured_at_source": "device_ntp",
            },
            headers={
                "X-Device-Id": "cam-01",
                "X-API-Key": RAW_CAMERA_KEY,
            },
        )
        assert resp.status_code == 200, f"Upload photo failed: {resp.text}"
        upload_result = resp.json()
        assert upload_result["status"] == "queued"
        photo_id = upload_result["photo_id"]

        # 4. List photos -- verify 1 photo
        resp = await client.get(
            "/api/hives/1/photos",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"List photos failed: {resp.text}"
        photos_data = resp.json()
        assert photos_data["total"] == 1
        assert photos_data["items"][0]["id"] == photo_id
        assert photos_data["items"][0]["ml_status"] == "pending"

    # 5. Run ML worker on the photo with mock YOLO (varroa detection, confidence 0.8)
    model = MockYolo(
        detections=[
            {"cls_id": 1, "conf": 0.8, "bbox": [10.0, 20.0, 50.0, 60.0]},
            {"cls_id": 0, "conf": 0.9, "bbox": [100.0, 100.0, 200.0, 200.0]},
        ]
    )
    result = await process_one(engine, model, photo_dir)
    assert result == photo_id, "ML worker should process our uploaded photo"

    # 6. Verify photo ml_status is now 'completed'
    async with AsyncSession(engine) as session:
        row = await session.execute(
            text("SELECT ml_status, ml_processed_at FROM photos WHERE id = :id"),
            {"id": photo_id},
        )
        photo_row = row.first()
        assert photo_row.ml_status == "completed"
        assert photo_row.ml_processed_at is not None

    # 7. List detections via API
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/hives/1/detections",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"List detections failed: {resp.text}"
        det_data = resp.json()
        assert det_data["total"] >= 1
        det = det_data["items"][0]
        assert det["photo_id"] == photo_id
        assert det["varroa_count"] == 1
        assert det["bee_count"] == 1
        assert det["top_confidence"] >= 0.8

    # 8. Run ML alerts -- verify VARROA_DETECTED fires (confidence 0.8 >= 0.7 threshold)
    alert_engine = AlertEngine(engine)
    alerts = await alert_engine.check_ml_alerts(hive_id=1)
    varroa_alerts = [a for a in alerts if a["type"] == "VARROA_DETECTED"]
    assert len(varroa_alerts) >= 1, "Expected VARROA_DETECTED alert to fire"
    assert varroa_alerts[0]["severity"] == "low"


# ---------------------------------------------------------------------------
# Test 2: Inspection CRUD with Sync Columns
# ---------------------------------------------------------------------------


async def test_inspection_crud_with_sync(integration_app):
    """Create -> Update -> List inspections, verify row_synced behavior."""
    app, engine, _photo_dir = integration_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create hive
        resp = await client.post(
            "/api/hives",
            json={"id": 1, "name": "Inspection Hive"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201

        # 2. POST /api/inspections (create)
        now = utc_now()
        resp = await client.post(
            "/api/inspections",
            json={
                "hive_id": 1,
                "inspected_at": now,
                "queen_seen": True,
                "brood_pattern": "good",
                "notes": "Initial inspection",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201, f"Create inspection failed: {resp.text}"
        insp_data = resp.json()
        insp_uuid = insp_data["uuid"]
        assert insp_data["queen_seen"] is True
        assert insp_data["brood_pattern"] == "good"
        assert insp_data["notes"] == "Initial inspection"
        assert insp_data["source"] == "local"

        # 3. Verify row_synced=0 in DB
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("SELECT row_synced, source FROM inspections WHERE uuid = :uuid"),
                {"uuid": insp_uuid},
            )
            row = result.first()
            assert row.row_synced == 0, "New inspection should have row_synced=0"
            assert row.source == "local"

        # 4. PUT /api/inspections/{uuid} (update notes)
        resp = await client.put(
            f"/api/inspections/{insp_uuid}",
            json={
                "hive_id": 1,
                "inspected_at": now,
                "queen_seen": False,
                "brood_pattern": "patchy",
                "notes": "Updated notes after second look",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"Update inspection failed: {resp.text}"
        updated = resp.json()
        assert updated["queen_seen"] is False
        assert updated["brood_pattern"] == "patchy"
        assert updated["notes"] == "Updated notes after second look"
        assert updated["source"] == "local"

        # 5. GET /api/hives/{id}/inspections -- verify updated data
        resp = await client.get(
            "/api/hives/1/inspections",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200, f"List inspections failed: {resp.text}"
        list_data = resp.json()
        assert list_data["total"] == 1
        item = list_data["items"][0]
        assert item["uuid"] == insp_uuid
        assert item["notes"] == "Updated notes after second look"
        assert item["queen_seen"] is False

    # 6. Verify source='local' and row_synced=0 after update
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT row_synced, source FROM inspections WHERE uuid = :uuid"),
            {"uuid": insp_uuid},
        )
        row = result.first()
        assert row.row_synced == 0, "Updated inspection should reset row_synced to 0"
        assert row.source == "local"


# ---------------------------------------------------------------------------
# Test 3: Photo Pruning Respects Sync
# ---------------------------------------------------------------------------


async def test_photo_pruning_respects_sync(integration_app):
    """Upload photo, verify pruning behavior respects sync status."""
    app, engine, photo_dir = integration_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create hive + camera
        resp = await client.post(
            "/api/hives",
            json={"id": 1, "name": "Prune Test Hive"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/admin/camera-nodes",
            json={
                "device_id": "cam-01",
                "hive_id": 1,
                "api_key": RAW_CAMERA_KEY,
            },
            headers={"X-Admin-Key": "admin-key"},
        )
        assert resp.status_code == 201

        # 2. Upload photo
        jpeg_data = _make_jpeg(500)
        resp = await client.post(
            "/api/photos/upload",
            files={"photo": ("prune.jpg", jpeg_data, "image/jpeg")},
            data={
                "hive_id": "1",
                "sequence": "0",
                "boot_id": "1",
            },
            headers={
                "X-Device-Id": "cam-01",
                "X-API-Key": RAW_CAMERA_KEY,
            },
        )
        assert resp.status_code == 200
        photo_id = resp.json()["photo_id"]

    # 3. Set ingested_at to 31 days ago, ml_status='completed'
    old_time = (datetime.now(UTC) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    async with AsyncSession(engine) as session:
        await session.execute(
            text(
                "UPDATE photos SET ingested_at = :ts, ml_status = 'completed' WHERE id = :id"
            ),
            {"ts": old_time, "id": photo_id},
        )
        await session.commit()

    # 4. Run prune_photos with cloud_sync_enabled=True -- photo NOT pruned (file_synced=0)
    pruned = await prune_photos(
        engine, photo_dir, retention_days=30, cloud_sync_enabled=True
    )
    assert pruned == 0, "Photo should NOT be pruned when cloud sync enabled and file_synced=0"

    # Verify photo still exists in DB
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM photos WHERE id = :id"),
            {"id": photo_id},
        )
        assert result.scalar() == 1, "Photo should still exist in DB"

    # 5. Run prune_photos with cloud_sync_enabled=False -- photo IS pruned
    pruned = await prune_photos(
        engine, photo_dir, retention_days=30, cloud_sync_enabled=False
    )
    assert pruned == 1, "Photo should be pruned when cloud sync disabled"

    # Verify photo is gone from DB
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM photos WHERE id = :id"),
            {"id": photo_id},
        )
        assert result.scalar() == 0, "Photo should be deleted from DB after pruning"


# ---------------------------------------------------------------------------
# Test 4: Webhook Dispatch on Critical Alert
# ---------------------------------------------------------------------------


async def test_webhook_dispatch_on_alert(integration_app):
    """Fire alert, run webhooks, verify delivery attempted and notified_at set."""
    app, engine, _photo_dir = integration_app

    # 1. Create hive
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Webhook Test Hive", created_at=utc_now())
        session.add(hive)
        await session.commit()

    # 2. Insert a critical alert with notified_at=NULL
    now = utc_now()
    async with AsyncSession(engine) as session:
        alert = Alert(
            hive_id=1,
            type="VARROA_HIGH_LOAD",
            severity="critical",
            message="Varroa load 5.2 mites/100 bees exceeds threshold",
            observed_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        alert_id = alert.id
        assert alert.notified_at is None

    # 3. Mock httpx.AsyncClient.post
    posted_urls = []
    posted_bodies = []

    async def mock_post(self, url, *, content=None, headers=None, **kwargs):
        posted_urls.append(str(url))
        posted_bodies.append(content)
        return type("Response", (), {"status_code": 200})()

    # 4. Call dispatch_webhooks
    with patch("httpx.AsyncClient.post", new=mock_post):
        async with AsyncSession(engine) as session:
            count = await dispatch_webhooks(
                session,
                ["http://hook1.example.com/webhook", "http://hook2.example.com/webhook"],
                "test-webhook-secret",
            )

    # 5. Verify the mock was called (delivery attempted)
    assert count == 1, "Should have dispatched 1 alert"
    assert len(posted_urls) == 2, "Should have posted to 2 webhook URLs"
    assert "http://hook1.example.com/webhook" in posted_urls
    assert "http://hook2.example.com/webhook" in posted_urls

    # 6. Verify alert notified_at is set
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT notified_at FROM alerts WHERE id = :id"),
            {"id": alert_id},
        )
        row = result.first()
        assert row.notified_at is not None, "notified_at should be set after dispatch"
