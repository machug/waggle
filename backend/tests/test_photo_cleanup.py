"""Tests for photo startup cleanup service."""

import os

import bcrypt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import CameraNode, Hive, Photo
from waggle.services.photo_cleanup import cleanup_photos
from waggle.utils.timestamps import utc_now


@pytest.fixture
async def setup_photo_env(tmp_path):
    """Create DB engine and photo directory with sentinel."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(db_url)
    await init_db(engine)

    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / ".waggle-sentinel").touch()

    # Create hive + camera node for foreign keys
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test", created_at=utc_now())
        session.add(hive)
        await session.flush()
        key_hash = bcrypt.hashpw(b"k", bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(
            device_id="cam-01", hive_id=1, api_key_hash=key_hash, created_at=utc_now()
        )
        session.add(node)
        await session.commit()

    yield engine, str(photo_dir)
    await engine.dispose()


def _create_photo_file(photo_dir: str, relative_path: str) -> str:
    """Helper: create a dummy .jpg file at the given relative path."""
    full_path = os.path.join(photo_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
    return full_path


async def _insert_photo_row(engine, photo_path: str, sequence: int = 1) -> int:
    """Helper: insert a Photo row and return its id."""
    now = utc_now()
    async with AsyncSession(engine) as session:
        photo = Photo(
            hive_id=1,
            device_id="cam-01",
            boot_id=1,
            captured_at=now,
            captured_at_source="ingested",
            sequence=sequence,
            photo_path=photo_path,
            file_size_bytes=54,
            sha256="a" * 64,
            width=800,
            height=600,
        )
        session.add(photo)
        await session.flush()
        photo_id = photo.id
        await session.commit()
        return photo_id


async def test_remove_tmp_files(setup_photo_env):
    """Pass 1: .tmp_* files in subfolders are removed."""
    engine, photo_dir = setup_photo_env

    # Create tmp files in root and subdirectory
    tmp1 = os.path.join(photo_dir, ".tmp_upload1")
    tmp2 = os.path.join(photo_dir, "hive_1", ".tmp_upload2")
    os.makedirs(os.path.dirname(tmp2), exist_ok=True)
    for p in (tmp1, tmp2):
        with open(p, "w") as f:
            f.write("partial")

    result = await cleanup_photos(engine, photo_dir)

    assert result["tmp_removed"] == 2
    assert not os.path.exists(tmp1)
    assert not os.path.exists(tmp2)


async def test_quarantine_orphan_files(setup_photo_env):
    """Pass 2: .jpg files with no DB row are moved to .quarantine/."""
    engine, photo_dir = setup_photo_env

    # Create orphan jpg files
    orphan_path = "hive_1/orphan.jpg"
    _create_photo_file(photo_dir, orphan_path)

    result = await cleanup_photos(engine, photo_dir)

    assert result["orphan_quarantined"] == 1
    # Original gone
    assert not os.path.exists(os.path.join(photo_dir, orphan_path))
    # Moved to quarantine
    quarantine_path = os.path.join(photo_dir, ".quarantine", orphan_path)
    assert os.path.exists(quarantine_path)


async def test_remove_dangling_rows(setup_photo_env):
    """Pass 3: DB rows whose files don't exist are deleted."""
    engine, photo_dir = setup_photo_env

    # Insert a photo row but don't create the file
    photo_id = await _insert_photo_row(engine, "hive_1/missing.jpg", sequence=1)

    result = await cleanup_photos(engine, photo_dir)

    assert result["dangling_removed"] == 1
    # Verify row is gone
    async with AsyncSession(engine) as session:
        row = await session.execute(select(Photo).where(Photo.id == photo_id))
        assert row.scalar_one_or_none() is None


async def test_sentinel_guard(setup_photo_env):
    """No sentinel file means cleanup returns all zeros, no changes."""
    engine, photo_dir = setup_photo_env

    # Remove sentinel
    os.unlink(os.path.join(photo_dir, ".waggle-sentinel"))

    # Create a tmp file that should NOT be cleaned up
    tmp_path = os.path.join(photo_dir, ".tmp_should_stay")
    with open(tmp_path, "w") as f:
        f.write("partial")

    result = await cleanup_photos(engine, photo_dir)

    assert result == {"tmp_removed": 0, "orphan_quarantined": 0, "dangling_removed": 0}
    # tmp file should still exist
    assert os.path.exists(tmp_path)


async def test_known_files_not_quarantined(setup_photo_env):
    """Files that match DB rows are left alone."""
    engine, photo_dir = setup_photo_env

    # Create file AND matching DB row
    rel_path = "hive_1/known.jpg"
    _create_photo_file(photo_dir, rel_path)
    await _insert_photo_row(engine, rel_path, sequence=10)

    result = await cleanup_photos(engine, photo_dir)

    assert result["orphan_quarantined"] == 0
    # File still in place
    assert os.path.exists(os.path.join(photo_dir, rel_path))


async def test_full_cleanup_all_passes(setup_photo_env):
    """All three passes run together correctly."""
    engine, photo_dir = setup_photo_env

    # Pass 1 target: tmp file
    tmp_path = os.path.join(photo_dir, "hive_1", ".tmp_partial")
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w") as f:
        f.write("partial")

    # Pass 2 target: orphan jpg (no DB row)
    orphan_rel = "hive_1/orphan.jpg"
    _create_photo_file(photo_dir, orphan_rel)

    # Pass 3 target: dangling DB row (no file)
    dangling_id = await _insert_photo_row(engine, "hive_1/gone.jpg", sequence=20)

    # Known file that should survive all passes
    known_rel = "hive_1/good.jpg"
    _create_photo_file(photo_dir, known_rel)
    await _insert_photo_row(engine, known_rel, sequence=30)

    result = await cleanup_photos(engine, photo_dir)

    assert result["tmp_removed"] == 1
    assert result["orphan_quarantined"] == 1
    assert result["dangling_removed"] == 1

    # Verify state
    assert not os.path.exists(tmp_path)
    assert not os.path.exists(os.path.join(photo_dir, orphan_rel))
    assert os.path.exists(os.path.join(photo_dir, ".quarantine", orphan_rel))

    async with AsyncSession(engine) as session:
        row = await session.execute(select(Photo).where(Photo.id == dangling_id))
        assert row.scalar_one_or_none() is None

    # Known file and its DB row still intact
    assert os.path.exists(os.path.join(photo_dir, known_rel))
    async with AsyncSession(engine) as session:
        row = await session.execute(select(Photo).where(Photo.photo_path == known_rel))
        assert row.scalar_one_or_none() is not None
