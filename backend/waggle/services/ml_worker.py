"""ML worker service — polls for pending photos and runs YOLOv8-nano inference."""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import MlDetection, Photo
from waggle.utils.timestamps import utc_now

logger = logging.getLogger(__name__)

# Cached model hash to avoid re-computing SHA256 on every call
_model_hash_cache: dict[str, str] = {}


def _compute_file_sha256(file_path: str) -> str:
    """Compute SHA256 hash of a file, with caching."""
    if file_path in _model_hash_cache:
        return _model_hash_cache[file_path]

    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _model_hash_cache[file_path] = digest
    return digest


def load_model(model_path: str, expected_hash: str | None = None):
    """Load a YOLOv8-nano model from model_path.

    If expected_hash is set, compute SHA256 of the model file and compare.
    Raises ValueError if hash mismatch.
    Returns the loaded YOLO model object.
    """
    if expected_hash is not None:
        actual_hash = _compute_file_sha256(model_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Model hash mismatch: expected {expected_hash}, got {actual_hash}")

    try:
        from ultralytics import YOLO  # noqa: I001
    except ImportError as exc:
        raise ImportError(
            "ultralytics is required for ML inference. Install with: pip install ultralytics"
        ) from exc

    model = YOLO(model_path)
    logger.info("Loaded model from %s", model_path)
    return model


def _parse_detections(results, model) -> list[dict]:
    """Parse YOLO results into a list of detection dicts.

    Each detection has: class (str), confidence (float), bbox ([x1, y1, x2, y2]).
    """
    detections = []
    if not results or len(results) == 0:
        return detections

    result = results[0]
    boxes = result.boxes

    cls_ids = boxes.cls
    confs = boxes.conf
    bboxes = boxes.xyxy

    names = model.names if hasattr(model, "names") else {}

    for i in range(len(cls_ids)):
        cls_id = int(cls_ids[i]) if not isinstance(cls_ids[i], int) else cls_ids[i]
        conf = float(confs[i]) if not isinstance(confs[i], float) else confs[i]
        bbox_raw = bboxes[i]
        bbox = [float(v) for v in bbox_raw] if not isinstance(bbox_raw, list) else bbox_raw

        class_name = names.get(cls_id, f"class_{cls_id}")
        detections.append(
            {
                "class": class_name,
                "confidence": round(conf, 4),
                "bbox": [round(v, 2) for v in bbox],
            }
        )

    return detections


async def recover_stale(engine) -> int:
    """Reset photos stuck in 'processing' for >10 minutes back to 'pending'.

    Returns the number of photos recovered.
    """
    async with AsyncSession(engine) as session:
        cutoff = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ] + "Z"
        result = await session.execute(
            text(
                "UPDATE photos SET ml_status='pending', ml_started_at=NULL "
                "WHERE ml_status='processing' AND ml_started_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        await session.commit()
        count = result.rowcount
        if count > 0:
            logger.info("Recovered %d stale processing photo(s)", count)
        return count


async def process_one(
    engine,
    model,
    photo_dir: str,
    confidence_threshold: float = 0.25,
    model_path: str | None = None,
) -> int | None:
    """Process one pending photo through ML inference.

    Returns the photo ID if processed, None if nothing to do or claimed by another worker.
    """
    async with AsyncSession(engine) as session:
        # 1. Query for next pending photo
        result = await session.execute(
            select(Photo)
            .where(Photo.ml_status == "pending")
            .order_by(Photo.ingested_at.asc(), Photo.id.asc())
            .limit(1)
        )
        photo = result.scalar_one_or_none()

        if photo is None:
            return None

        photo_id = photo.id
        photo_hive_id = photo.hive_id
        photo_path = photo.photo_path
        photo_attempts = photo.ml_attempts

        # 2. Atomically claim the photo
        claim_result = await session.execute(
            text(
                "UPDATE photos SET ml_status='processing', "
                "ml_started_at=:now, ml_attempts=ml_attempts+1 "
                "WHERE id=:photo_id AND ml_status='pending'"
            ),
            {"now": utc_now(), "photo_id": photo_id},
        )
        await session.commit()

        if claim_result.rowcount == 0:
            # Another worker claimed it
            return None

    # Re-read attempts after increment
    current_attempts = photo_attempts + 1

    # 3. Build full path and run inference
    full_path = os.path.join(photo_dir, photo_path)

    try:
        # Time the inference
        t_start = time.monotonic()
        results = await asyncio.to_thread(model, str(full_path), verbose=False)
        t_end = time.monotonic()
        inference_ms = max(1, int((t_end - t_start) * 1000))

        # 4. Parse all detections (raw, before filtering)
        all_detections = _parse_detections(results, model)

        # 5. Compute varroa_max_confidence from ALL detections (before filtering)
        varroa_confs = [d["confidence"] for d in all_detections if d["class"] == "varroa"]
        varroa_max_confidence = max(varroa_confs) if varroa_confs else 0.0

        # 6. Filter detections by confidence threshold
        filtered_detections = [
            d for d in all_detections if d["confidence"] >= confidence_threshold
        ]

        # 7. Count per class
        bee_count = sum(1 for d in filtered_detections if d["class"] == "bee")
        varroa_count = sum(1 for d in filtered_detections if d["class"] == "varroa")
        pollen_count = sum(1 for d in filtered_detections if d["class"] == "pollen")
        wasp_count = sum(1 for d in filtered_detections if d["class"] == "wasp")

        # 8. Determine top_class
        if not filtered_detections:
            top_class = "normal"
            top_confidence = 0.0
        else:
            best = max(filtered_detections, key=lambda d: d["confidence"])
            top_class = best["class"]
            top_confidence = best["confidence"]

        # 9. Model metadata
        model_version = "yolov8n-waggle-v1"
        if hasattr(model, "model_name"):
            model_version = model.model_name

        if model_path:
            model_hash = _compute_file_sha256(model_path)
        elif hasattr(model, "model_hash"):
            model_hash = model.model_hash
        else:
            model_hash = "unknown"

        # 10. Insert detection and update photo
        async with AsyncSession(engine) as session:
            detection = MlDetection(
                photo_id=photo_id,
                hive_id=photo_hive_id,
                detected_at=utc_now(),
                top_class=top_class,
                top_confidence=top_confidence,
                detections_json=json.dumps(filtered_detections),
                varroa_count=varroa_count,
                pollen_count=pollen_count,
                wasp_count=wasp_count,
                bee_count=bee_count,
                varroa_max_confidence=varroa_max_confidence,
                inference_ms=inference_ms,
                model_version=model_version,
                model_hash=model_hash,
            )
            session.add(detection)

            await session.execute(
                text(
                    "UPDATE photos SET ml_status='completed', "
                    "ml_processed_at=:now, ml_error=NULL "
                    "WHERE id=:photo_id"
                ),
                {"now": utc_now(), "photo_id": photo_id},
            )
            await session.commit()

        logger.info(
            "Processed photo %d: top_class=%s confidence=%.3f bees=%d varroa=%d inference=%dms",
            photo_id,
            top_class,
            top_confidence,
            bee_count,
            varroa_count,
            inference_ms,
        )
        return photo_id

    except Exception as exc:
        logger.exception("Error processing photo %d: %s", photo_id, exc)

        async with AsyncSession(engine) as session:
            if current_attempts >= 3:
                # Permanent failure
                await session.execute(
                    text(
                        "UPDATE photos SET ml_status='failed', ml_error=:error WHERE id=:photo_id"
                    ),
                    {"error": str(exc), "photo_id": photo_id},
                )
            else:
                # Retry: reset to pending
                await session.execute(
                    text(
                        "UPDATE photos SET ml_status='pending', "
                        "ml_started_at=NULL WHERE id=:photo_id"
                    ),
                    {"photo_id": photo_id},
                )
            await session.commit()

        return None


async def run_worker(
    db_url: str,
    photo_dir: str,
    model_path: str,
    *,
    expected_hash: str | None = None,
    confidence_threshold: float = 0.25,
    poll_interval: float = 2.0,
    max_iterations: int | None = None,
) -> None:
    """Main entry point that runs the polling loop.

    Args:
        db_url: SQLAlchemy async database URL.
        photo_dir: Base directory for photo files.
        model_path: Path to the YOLO model file.
        expected_hash: Expected SHA256 hash of the model file.
        confidence_threshold: Minimum confidence to include a detection.
        poll_interval: Seconds to sleep when no pending photos found.
        max_iterations: Stop after N iterations (for testing). None = run forever.
    """
    logger.info("Starting ML worker: model=%s photo_dir=%s", model_path, photo_dir)

    model = load_model(model_path, expected_hash=expected_hash)

    engine = create_engine_from_url(db_url, is_worker=True)
    await init_db(engine)

    # Startup recovery
    await recover_stale(engine)
    last_recovery = time.monotonic()

    iteration = 0
    try:
        while True:
            if max_iterations is not None and iteration >= max_iterations:
                break

            # Periodic recovery every 60 seconds
            if time.monotonic() - last_recovery >= 60:
                await recover_stale(engine)
                last_recovery = time.monotonic()

            result = await process_one(
                engine,
                model,
                photo_dir,
                confidence_threshold=confidence_threshold,
                model_path=model_path,
            )

            if result is None:
                await asyncio.sleep(poll_interval)

            iteration += 1
    finally:
        await engine.dispose()
        logger.info("ML worker stopped after %d iterations", iteration)
