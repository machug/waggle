"""Photo pruning — removes old photos that have been synced and processed."""

import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Photo

logger = logging.getLogger(__name__)


async def prune_photos(
    engine,
    photo_dir: str,
    retention_days: int = 30,
    cloud_sync_enabled: bool = False,
) -> int:
    """Prune photos older than retention_days that meet all conditions.

    A photo is prunable when ALL conditions are met:
    1. file_synced = 1 (or cloud sync disabled)
    2. row_synced = 1 (or cloud sync disabled)
    3. ml_status IN ('completed', 'failed')
    4. ingested_at < retention_cutoff

    Returns the number of photos pruned.
    """
    # Sentinel guard
    sentinel = os.path.join(photo_dir, ".waggle-sentinel")
    if not os.path.exists(sentinel):
        logger.warning("Photo storage unavailable, skipping pruning")
        return 0

    cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
        :-3
    ] + "Z"

    async with AsyncSession(engine) as session:
        # Build query for prunable photos
        query = select(Photo).where(
            Photo.ml_status.in_(["completed", "failed"]),
            Photo.ingested_at < cutoff,
        )

        if cloud_sync_enabled:
            query = query.where(
                Photo.file_synced == 1,
                Photo.row_synced == 1,
            )

        result = await session.execute(query)
        photos = result.scalars().all()

        count = 0
        for photo in photos:
            full_path = os.path.join(photo_dir, photo.photo_path)

            # Delete file
            if os.path.exists(full_path):
                try:
                    os.unlink(full_path)
                except OSError:
                    logger.warning("Failed to delete photo file: %s", full_path)
                    continue

            # Delete DB row (CASCADE deletes ml_detections)
            await session.execute(
                text("DELETE FROM photos WHERE id = :id"),
                {"id": photo.id},
            )
            count += 1

        await session.commit()

    if count > 0:
        logger.info("Pruned %d photo(s) older than %d days", count, retention_days)

    return count
