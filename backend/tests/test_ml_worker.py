"""Tests for ML worker service."""

import json
from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import CameraNode, Hive, MlDetection, Photo
from waggle.services.ml_worker import process_one, recover_stale
from waggle.utils.timestamps import utc_now

# ---------------------------------------------------------------------------
# Mock YOLO model objects — no torch/ultralytics dependency
# ---------------------------------------------------------------------------


class MockBoxes:
    """Simulates ultralytics Results.boxes object using plain Python lists."""

    def __init__(self, detections):
        self._detections = detections

    @property
    def cls(self):
        return [d["cls_id"] for d in self._detections]

    @property
    def conf(self):
        return [d["conf"] for d in self._detections]

    @property
    def xyxy(self):
        return [d["bbox"] for d in self._detections]


class MockYoloResult:
    """Simulates one ultralytics Results object."""

    def __init__(self, detections):
        self.boxes = MockBoxes(detections)


class MockYoloModel:
    """Mock YOLO model for testing — no ultralytics needed.

    ``detections`` is a list of dicts with keys: cls_id (int), conf (float), bbox (list).
    ``names`` maps int class IDs to human-readable names.
    """

    def __init__(self, detections=None, *, fail=False, model_hash="mock-hash-abc123"):
        self.detections = detections or []
        self.fail = fail
        self.names = {0: "bee", 1: "varroa", 2: "pollen", 3: "wasp"}
        self.model_hash = model_hash

    def __call__(self, image_path, verbose=False):
        if self.fail:
            raise RuntimeError("Mock inference failure")
        result = MockYoloResult(self.detections)
        return [result]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_with_photo(tmp_path):
    """Create DB with hive + camera_node + pending photo on disk."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    # Create a fake photo file
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    sentinel = photo_dir / ".waggle-sentinel"
    sentinel.touch()
    relative_path = "1/2026-02-08/cam-01_1_0_test.jpg"
    full_dir = photo_dir / "1" / "2026-02-08"
    full_dir.mkdir(parents=True)
    photo_file = full_dir / "cam-01_1_0_test.jpg"
    # Write minimal JPEG bytes
    photo_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

    async with AsyncSession(engine) as session:
        # Create hive
        hive = Hive(id=1, name="Test Hive", created_at=utc_now())
        session.add(hive)
        await session.flush()

        # Create camera node
        key_hash = bcrypt.hashpw(b"test-key", bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(
            device_id="cam-01",
            hive_id=1,
            api_key_hash=key_hash,
            created_at=utc_now(),
        )
        session.add(node)
        await session.flush()

        # Create pending photo
        photo = Photo(
            hive_id=1,
            device_id="cam-01",
            boot_id=1,
            captured_at=utc_now(),
            captured_at_source="device_rtc",
            ingested_at=utc_now(),
            sequence=0,
            photo_path=relative_path,
            file_size_bytes=103,
            sha256="abc123",
        )
        session.add(photo)
        await session.commit()

    yield engine, str(photo_dir)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_process_pending_photo(db_with_photo):
    """Mock YOLO returns 2 bees — photo should go pending -> completed."""
    engine, photo_dir = db_with_photo
    model = MockYoloModel(
        detections=[
            {"cls_id": 0, "conf": 0.9, "bbox": [10.0, 20.0, 30.0, 40.0]},
            {"cls_id": 0, "conf": 0.8, "bbox": [50.0, 60.0, 70.0, 80.0]},
        ]
    )

    result = await process_one(engine, model, photo_dir)
    assert result is not None  # should return photo id

    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo).where(Photo.id == result))).scalar_one()
        assert photo.ml_status == "completed"
        assert photo.ml_processed_at is not None

        detection = (
            await session.execute(select(MlDetection).where(MlDetection.photo_id == result))
        ).scalar_one()
        assert detection.top_class == "bee"
        assert detection.bee_count == 2
        assert detection.top_confidence >= 0.8
        parsed = json.loads(detection.detections_json)
        assert len(parsed) == 2


async def test_process_no_pending_returns_none(db_with_photo):
    """When no pending photos exist, process_one should return None."""
    engine, photo_dir = db_with_photo

    # Mark the existing photo as completed so nothing is pending
    async with AsyncSession(engine) as session:
        await session.execute(
            select(Photo).where(Photo.ml_status == "pending")  # just to verify it exists
        )
        from sqlalchemy import text

        await session.execute(text("UPDATE photos SET ml_status='completed'"))
        await session.commit()

    model = MockYoloModel()
    result = await process_one(engine, model, photo_dir)
    assert result is None


async def test_process_failure_retry(db_with_photo):
    """First failure: ml_attempts goes to 1, ml_status back to pending for retry."""
    engine, photo_dir = db_with_photo
    model = MockYoloModel(fail=True)

    result = await process_one(engine, model, photo_dir)
    assert result is None  # failure returns None

    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo).limit(1))).scalar_one()
        assert photo.ml_attempts == 1
        assert photo.ml_status == "pending"  # reset for retry
        assert photo.ml_started_at is None


async def test_process_permanent_failure(db_with_photo):
    """Photo with ml_attempts=2 + mock fails => attempts=3, status=failed."""
    engine, photo_dir = db_with_photo

    # Set ml_attempts to 2 so next failure hits the threshold
    async with AsyncSession(engine) as session:
        from sqlalchemy import text

        await session.execute(text("UPDATE photos SET ml_attempts=2"))
        await session.commit()

    model = MockYoloModel(fail=True)
    result = await process_one(engine, model, photo_dir)
    assert result is None

    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo).limit(1))).scalar_one()
        assert photo.ml_attempts == 3
        assert photo.ml_status == "failed"
        assert photo.ml_error is not None
        assert "Mock inference failure" in photo.ml_error


async def test_varroa_max_confidence(db_with_photo):
    """varroa_max_confidence should reflect raw (unfiltered) detections.

    With confidence_threshold=0.7:
    - bee at 0.9 passes filter
    - varroa at 0.6 does NOT pass filter
    - varroa_max_confidence should still be 0.6
    """
    engine, photo_dir = db_with_photo
    model = MockYoloModel(
        detections=[
            {"cls_id": 0, "conf": 0.9, "bbox": [10.0, 20.0, 30.0, 40.0]},
            {"cls_id": 1, "conf": 0.6, "bbox": [50.0, 60.0, 70.0, 80.0]},
        ]
    )

    result = await process_one(engine, model, photo_dir, confidence_threshold=0.7)
    assert result is not None

    async with AsyncSession(engine) as session:
        detection = (
            await session.execute(select(MlDetection).where(MlDetection.photo_id == result))
        ).scalar_one()
        # varroa_max_confidence from raw detections (varroa at 0.6)
        assert detection.varroa_max_confidence == pytest.approx(0.6, abs=0.01)
        # Filtered: only bee at 0.9 passes threshold 0.7
        assert detection.varroa_count == 0
        assert detection.bee_count == 1
        assert detection.top_class == "bee"


async def test_no_detections_normal(db_with_photo):
    """Empty YOLO results should produce top_class='normal', top_confidence=0.0."""
    engine, photo_dir = db_with_photo
    model = MockYoloModel(detections=[])

    result = await process_one(engine, model, photo_dir)
    assert result is not None

    async with AsyncSession(engine) as session:
        detection = (
            await session.execute(select(MlDetection).where(MlDetection.photo_id == result))
        ).scalar_one()
        assert detection.top_class == "normal"
        assert detection.top_confidence == pytest.approx(0.0)
        assert detection.bee_count == 0
        assert detection.varroa_count == 0


async def test_atomic_claim(db_with_photo):
    """Two calls to process_one with same pending photo: first claims, second gets None."""
    engine, photo_dir = db_with_photo
    model = MockYoloModel(
        detections=[
            {"cls_id": 0, "conf": 0.85, "bbox": [10.0, 20.0, 30.0, 40.0]},
        ]
    )

    # First call should claim and process
    result1 = await process_one(engine, model, photo_dir)
    assert result1 is not None

    # Second call: no pending photos left
    result2 = await process_one(engine, model, photo_dir)
    assert result2 is None


# ---------------------------------------------------------------------------
# Crash recovery tests
# ---------------------------------------------------------------------------


async def test_recover_stale_resets_processing(db_with_photo):
    """Photo stuck in 'processing' for 15 min should be reset to 'pending'."""
    engine, _photo_dir = db_with_photo

    stale_time = (datetime.now(UTC) - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
        :-3
    ] + "Z"

    async with AsyncSession(engine) as session:
        await session.execute(
            text("UPDATE photos SET ml_status='processing', ml_started_at=:ts"),
            {"ts": stale_time},
        )
        await session.commit()

    count = await recover_stale(engine)
    assert count == 1

    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo).limit(1))).scalar_one()
        assert photo.ml_status == "pending"
        assert photo.ml_started_at is None


async def test_recover_stale_ignores_recent(db_with_photo):
    """Photo in 'processing' for only 5 min should NOT be reset."""
    engine, _photo_dir = db_with_photo

    recent_time = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
        :-3
    ] + "Z"

    async with AsyncSession(engine) as session:
        await session.execute(
            text("UPDATE photos SET ml_status='processing', ml_started_at=:ts"),
            {"ts": recent_time},
        )
        await session.commit()

    count = await recover_stale(engine)
    assert count == 0

    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo).limit(1))).scalar_one()
        assert photo.ml_status == "processing"


async def test_recover_stale_ignores_other_statuses(db_with_photo):
    """Photos with ml_status='pending' should be untouched by recovery."""
    engine, _photo_dir = db_with_photo

    # Photo starts as 'pending' by default from the fixture — leave it as-is
    count = await recover_stale(engine)
    assert count == 0

    async with AsyncSession(engine) as session:
        photo = (await session.execute(select(Photo).limit(1))).scalar_one()
        assert photo.ml_status == "pending"
