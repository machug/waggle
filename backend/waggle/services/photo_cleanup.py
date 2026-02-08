"""Photo startup cleanup — reconciles filesystem and database state."""

import logging
import os
import shutil

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Photo

logger = logging.getLogger(__name__)


async def cleanup_photos(engine, photo_dir: str) -> dict:
    """Run all three cleanup passes.

    Returns a summary dict with counts for each pass:
    {
        "tmp_removed": int,
        "orphan_quarantined": int,
        "dangling_removed": int,
    }
    """
    # Sentinel guard
    sentinel = os.path.join(photo_dir, ".waggle-sentinel")
    if not os.path.exists(sentinel):
        logger.warning("Photo storage unavailable (missing sentinel), skipping cleanup")
        return {"tmp_removed": 0, "orphan_quarantined": 0, "dangling_removed": 0}

    tmp_count = _remove_tmp_files(photo_dir)
    orphan_count = await _quarantine_orphan_files(engine, photo_dir)
    dangling_count = await _remove_dangling_rows(engine, photo_dir)

    return {
        "tmp_removed": tmp_count,
        "orphan_quarantined": orphan_count,
        "dangling_removed": dangling_count,
    }


def _remove_tmp_files(photo_dir: str) -> int:
    """Pass 1: Remove orphan .tmp_* files from incomplete uploads."""
    count = 0
    for dirpath, _dirnames, filenames in os.walk(photo_dir):
        for fname in filenames:
            if fname.startswith(".tmp_"):
                full_path = os.path.join(dirpath, fname)
                try:
                    os.unlink(full_path)
                    count += 1
                    logger.debug("Removed tmp file: %s", full_path)
                except OSError:
                    logger.warning("Failed to remove tmp file: %s", full_path)
    if count > 0:
        logger.info("Removed %d orphan tmp file(s)", count)
    return count


async def _quarantine_orphan_files(engine, photo_dir: str) -> int:
    """Pass 2: Move files that have no DB row to quarantine directory."""
    quarantine_dir = os.path.join(photo_dir, ".quarantine")
    count = 0

    # Get all photo_path values from DB
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo.photo_path))
        db_paths = {row[0] for row in result.all()}

    # Walk filesystem looking for .jpg files
    for dirpath, _dirnames, filenames in os.walk(photo_dir):
        # Skip quarantine dir and hidden dirs
        rel_dir = os.path.relpath(dirpath, photo_dir)
        if rel_dir.startswith("."):
            continue

        for fname in filenames:
            if not fname.endswith(".jpg"):
                continue
            if fname.startswith(".tmp_"):
                continue  # Already handled by pass 1

            full_path = os.path.join(dirpath, fname)
            relative_path = os.path.relpath(full_path, photo_dir)

            if relative_path not in db_paths:
                # Move to quarantine
                quarantine_path = os.path.join(quarantine_dir, relative_path)
                os.makedirs(os.path.dirname(quarantine_path), exist_ok=True)
                try:
                    shutil.move(full_path, quarantine_path)
                    count += 1
                    logger.debug("Quarantined orphan file: %s", relative_path)
                except OSError:
                    logger.warning("Failed to quarantine: %s", relative_path)

    if count > 0:
        logger.info("Quarantined %d orphan file(s)", count)
    return count


async def _remove_dangling_rows(engine, photo_dir: str) -> int:
    """Pass 3: Remove DB rows whose files are missing from disk."""
    count = 0
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Photo.id, Photo.photo_path))
        rows = result.all()

        for photo_id, photo_path in rows:
            full_path = os.path.join(photo_dir, photo_path)
            if not os.path.exists(full_path):
                await session.execute(
                    text("DELETE FROM photos WHERE id = :id"),
                    {"id": photo_id},
                )
                count += 1
                logger.debug("Removed dangling DB row for photo %d: %s", photo_id, photo_path)

        await session.commit()

    if count > 0:
        logger.info("Removed %d dangling DB row(s)", count)
    return count
