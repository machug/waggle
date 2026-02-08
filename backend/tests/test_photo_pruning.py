"""Tests for photo pruning service."""

import os
from datetime import UTC, datetime, timedelta
from random import randint
from uuid import uuid4

import bcrypt
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import CameraNode, Hive, MlDetection, Photo
from waggle.services.photo_pruning import prune_photos
from waggle.utils.timestamps import utc_now


@pytest.fixture
async def setup_prune_env(tmp_path):
    """Create a test database and photo directory with sentinel."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / ".waggle-sentinel").touch()

    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test", created_at=utc_now())
        session.add(hive)
        await session.flush()
        key_hash = bcrypt.hashpw(b"k", bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(
            device_id="cam-01",
            hive_id=1,
            api_key_hash=key_hash,
            created_at=utc_now(),
        )
        session.add(node)
        await session.commit()

    yield engine, str(photo_dir)
    await engine.dispose()


async def _create_photo(
    engine,
    photo_dir,
    ingested_at,
    ml_status="completed",
    file_synced=0,
    row_synced=0,
):
    """Helper to create a photo record with matching file."""
    relative_path = f"1/2026-02-08/cam-01_1_{uuid4().hex[:8]}.jpg"
    full_path = os.path.join(photo_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(b"\xff\xd8\xff" + b"\x00" * 100)

    seq = randint(0, 65535)
    async with AsyncSession(engine) as session:
        photo = Photo(
            hive_id=1,
            device_id="cam-01",
            boot_id=1,
            captured_at=utc_now(),
            captured_at_source="device_rtc",
            ingested_at=ingested_at,
            sequence=seq,
            photo_path=relative_path,
            file_size_bytes=103,
            sha256=uuid4().hex,
            ml_status=ml_status,
            file_synced=file_synced,
            row_synced=row_synced,
        )
        session.add(photo)
        await session.commit()
        await session.refresh(photo)
        return photo.id, full_path


def _days_ago(days: int) -> str:
    """Return an ISO 8601 timestamp for N days ago."""
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def test_prune_old_completed_photos(setup_prune_env):
    """Photo older than retention with ml_status='completed' is pruned."""
    engine, photo_dir = setup_prune_env
    photo_id, full_path = await _create_photo(
        engine, photo_dir, ingested_at=_days_ago(31), ml_status="completed"
    )

    count = await prune_photos(engine, photo_dir, retention_days=30)

    assert count == 1
    assert not os.path.exists(full_path)

    # Verify DB row is gone
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo).where(Photo.id == photo_id))
        assert result.scalar_one_or_none() is None


async def test_prune_respects_retention(setup_prune_env):
    """Photo newer than retention period is not pruned."""
    engine, photo_dir = setup_prune_env
    photo_id, full_path = await _create_photo(
        engine, photo_dir, ingested_at=_days_ago(10), ml_status="completed"
    )

    count = await prune_photos(engine, photo_dir, retention_days=30)

    assert count == 0
    assert os.path.exists(full_path)

    # Verify DB row still exists
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo).where(Photo.id == photo_id))
        assert result.scalar_one_or_none() is not None


async def test_prune_requires_ml_completion(setup_prune_env):
    """Photo older than retention but ml_status='pending' is not pruned."""
    engine, photo_dir = setup_prune_env
    photo_id, full_path = await _create_photo(
        engine, photo_dir, ingested_at=_days_ago(31), ml_status="pending"
    )

    count = await prune_photos(engine, photo_dir, retention_days=30)

    assert count == 0
    assert os.path.exists(full_path)

    # Verify DB row still exists
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo).where(Photo.id == photo_id))
        assert result.scalar_one_or_none() is not None


async def test_prune_with_sync_enabled(setup_prune_env):
    """With cloud_sync_enabled=True, only fully-synced photos are pruned."""
    engine, photo_dir = setup_prune_env

    # Unsynced photo — should NOT be pruned
    unsynced_id, unsynced_path = await _create_photo(
        engine,
        photo_dir,
        ingested_at=_days_ago(31),
        ml_status="completed",
        file_synced=0,
        row_synced=0,
    )

    # Fully synced photo — should be pruned
    synced_id, synced_path = await _create_photo(
        engine,
        photo_dir,
        ingested_at=_days_ago(31),
        ml_status="completed",
        file_synced=1,
        row_synced=1,
    )

    count = await prune_photos(engine, photo_dir, retention_days=30, cloud_sync_enabled=True)

    assert count == 1
    # Unsynced still present
    assert os.path.exists(unsynced_path)
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo).where(Photo.id == unsynced_id))
        assert result.scalar_one_or_none() is not None

    # Synced is gone
    assert not os.path.exists(synced_path)
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo).where(Photo.id == synced_id))
        assert result.scalar_one_or_none() is None


async def test_prune_without_sync(setup_prune_env):
    """With cloud_sync_enabled=False, unsynced photos are still pruned."""
    engine, photo_dir = setup_prune_env
    photo_id, full_path = await _create_photo(
        engine,
        photo_dir,
        ingested_at=_days_ago(31),
        ml_status="completed",
        file_synced=0,
        row_synced=0,
    )

    count = await prune_photos(engine, photo_dir, retention_days=30, cloud_sync_enabled=False)

    assert count == 1
    assert not os.path.exists(full_path)

    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo).where(Photo.id == photo_id))
        assert result.scalar_one_or_none() is None


async def test_sentinel_guard(setup_prune_env):
    """Without sentinel file, pruning returns 0 and does nothing."""
    engine, photo_dir = setup_prune_env
    # Remove sentinel
    os.unlink(os.path.join(photo_dir, ".waggle-sentinel"))

    photo_id, full_path = await _create_photo(
        engine, photo_dir, ingested_at=_days_ago(31), ml_status="completed"
    )

    count = await prune_photos(engine, photo_dir, retention_days=30)

    assert count == 0
    assert os.path.exists(full_path)


async def test_prune_cascade_deletes_detection(setup_prune_env):
    """Pruning a photo also deletes its MlDetection row via CASCADE."""
    engine, photo_dir = setup_prune_env
    photo_id, full_path = await _create_photo(
        engine, photo_dir, ingested_at=_days_ago(31), ml_status="completed"
    )

    # Insert an MlDetection row for this photo
    async with AsyncSession(engine) as session:
        detection = MlDetection(
            photo_id=photo_id,
            hive_id=1,
            detected_at=utc_now(),
            top_class="normal",
            top_confidence=0.95,
            detections_json="[]",
            varroa_count=0,
            pollen_count=0,
            wasp_count=0,
            bee_count=3,
            varroa_max_confidence=0.0,
            inference_ms=150,
            model_version="yolov8n-waggle-v1",
            model_hash="abc123",
        )
        session.add(detection)
        await session.flush()
        detection_id = detection.id
        await session.commit()

    count = await prune_photos(engine, photo_dir, retention_days=30)

    assert count == 1
    assert not os.path.exists(full_path)

    # Verify both photo and detection are gone
    async with AsyncSession(engine) as session:
        photo_result = await session.execute(select(Photo).where(Photo.id == photo_id))
        assert photo_result.scalar_one_or_none() is None

        detection_result = await session.execute(
            text("SELECT id FROM ml_detections WHERE id = :id"),
            {"id": detection_id},
        )
        assert detection_result.first() is None
