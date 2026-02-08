"""Photo upload and serving router."""

import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import CameraNode, Photo
from waggle.utils.timestamps import utc_now


def create_router(verify_key) -> APIRouter:
    router = APIRouter()

    @router.post("/photos/upload")
    async def upload_photo(
        request: Request,
        photo: UploadFile = File(...),
        hive_id: int = Form(...),
        sequence: int = Form(...),
        boot_id: int = Form(...),
        captured_at: str = Form(""),
        captured_at_source: str = Form(""),
    ):
        settings = (
            request.app.state.settings if hasattr(request.app.state, "settings") else None
        )
        photo_dir = (
            getattr(settings, "PHOTO_DIR", None)
            or os.environ.get("PHOTO_DIR", "/var/lib/waggle/photos")
        )
        max_photo_size = getattr(settings, "MAX_PHOTO_SIZE", None) or 204800
        max_queue_depth = getattr(settings, "MAX_QUEUE_DEPTH", None) or 50
        disk_threshold = getattr(settings, "DISK_USAGE_THRESHOLD", None) or 0.90

        # 1. Sentinel guard
        sentinel = os.path.join(photo_dir, ".waggle-sentinel")
        if not os.path.exists(sentinel):
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "STORAGE_UNAVAILABLE",
                        "message": "Photo storage is unavailable",
                    }
                },
            )

        # 2. Validate device auth
        device_id = request.headers.get("X-Device-Id")
        device_key = request.headers.get("X-API-Key")
        if not device_id or not device_key:
            raise HTTPException(status_code=401, detail="Missing or invalid device credentials")

        async with AsyncSession(request.app.state.engine) as session:
            node = await session.get(CameraNode, device_id)
            if not node:
                raise HTTPException(status_code=404, detail="Device not registered")

            # 3. Validate API key against bcrypt hash
            if not bcrypt.checkpw(
                device_key.encode("utf-8"), node.api_key_hash.encode("utf-8")
            ):
                raise HTTPException(
                    status_code=401, detail="Missing or invalid device credentials"
                )

            # 4. Validate hive binding
            if node.hive_id != hive_id:
                raise HTTPException(
                    status_code=400, detail="hive_id does not match device binding"
                )

            # 5. Read file and validate JPEG magic bytes
            data = await photo.read(max_photo_size + 1)
            if len(data) < 3 or data[:3] != b"\xff\xd8\xff":
                raise HTTPException(status_code=400, detail="Not a valid JPEG")

            # 6. Size enforcement
            if len(data) > max_photo_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"Photo exceeds maximum size of {max_photo_size} bytes",
                )

            # 7. SHA256
            sha256 = hashlib.sha256(data).hexdigest()

            # 8. Idempotency check (before rate limiting)
            existing = (
                await session.execute(
                    select(Photo.id).where(
                        Photo.device_id == device_id,
                        Photo.boot_id == boot_id,
                        Photo.sequence == sequence,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return {"photo_id": existing, "status": "duplicate"}

            # 9. Rate limit: >10/min/hive
            one_min_ago = (
                (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                + "Z"
            )
            rate_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Photo)
                    .where(
                        Photo.hive_id == hive_id,
                        Photo.ingested_at >= one_min_ago,
                    )
                )
            ).scalar()
            if rate_count >= 10:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {"code": "RATE_LIMITED", "message": "Upload rate limit exceeded"}
                    },
                    headers={"Retry-After": "60"},
                )

            # 10. Queue backpressure
            queue_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Photo)
                    .where(Photo.ml_status.in_(["pending", "processing"]))
                )
            ).scalar()
            if queue_count >= max_queue_depth:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {"code": "RATE_LIMITED", "message": "ML queue depth exceeded"}
                    },
                    headers={"Retry-After": "60"},
                )

            # 11. Disk usage check
            try:
                usage = shutil.disk_usage(photo_dir)
                if usage.used / usage.total >= disk_threshold:
                    return JSONResponse(
                        status_code=507,
                        content={
                            "error": {
                                "code": "STORAGE_FULL",
                                "message": "Disk usage exceeds threshold",
                            }
                        },
                    )
            except OSError:
                pass  # If we can't check, proceed

            # 12. Normalize captured_at / captured_at_source
            now = utc_now()
            if not captured_at or not captured_at.strip():
                captured_at = now
                captured_at_source = "ingested"
            elif not captured_at_source or not captured_at_source.strip():
                captured_at_source = "device_rtc"

            # 13. Generate storage path
            date_str = now[:10]  # YYYY-MM-DD
            sanitized_ts = captured_at.replace(":", "-")
            relative_path = (
                f"{hive_id}/{date_str}/{device_id}_{boot_id}_{sequence}_{sanitized_ts}.jpg"
            )
            full_path = os.path.join(photo_dir, relative_path)
            dir_path = os.path.dirname(full_path)

            # 14. Atomic write
            os.makedirs(dir_path, exist_ok=True)
            tmp_name = f".tmp_{uuid.uuid4()}.jpg"
            tmp_path = os.path.join(dir_path, tmp_name)

            try:
                # Write temp file
                with open(tmp_path, "wb") as f:
                    f.write(data)

                # Insert DB row
                try:
                    photo_row = Photo(
                        hive_id=hive_id,
                        device_id=device_id,
                        boot_id=boot_id,
                        captured_at=captured_at,
                        captured_at_source=captured_at_source,
                        ingested_at=now,
                        sequence=sequence,
                        photo_path=relative_path,
                        file_size_bytes=len(data),
                        sha256=sha256,
                    )
                    session.add(photo_row)
                    await session.flush()
                    photo_id = photo_row.id
                except IntegrityError:
                    await session.rollback()
                    # Race condition: duplicate detected at DB level
                    existing = (
                        await session.execute(
                            select(Photo.id).where(
                                Photo.device_id == device_id,
                                Photo.boot_id == boot_id,
                                Photo.sequence == sequence,
                            )
                        )
                    ).scalar_one_or_none()
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    return {"photo_id": existing, "status": "duplicate"}

                # Rename temp to final
                os.rename(tmp_path, full_path)

                # 15. Update last_seen_at
                node.last_seen_at = now
                await session.commit()

                return {"photo_id": photo_id, "status": "queued"}
            except Exception:
                # Cleanup on failure
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                if os.path.exists(full_path):
                    os.unlink(full_path)
                await session.rollback()
                raise

    return router
