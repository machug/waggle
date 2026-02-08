"""Tests for photo upload endpoint."""

import os

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import CameraNode, Hive, Photo
from waggle.routers import photos
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key"
DEVICE_KEY = "a" * 32
DEVICE_ID = "cam-test-01"

# Minimal valid JPEG: FF D8 FF E0 + minimal JFIF header + padding
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture
async def app_with_camera(tmp_path):
    """Create app with a hive, camera node, and photo directory."""
    db_path = tmp_path / "test.db"
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # Create sentinel
    (photo_dir / ".waggle-sentinel").write_text("waggle photo storage sentinel")

    application = create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key=API_KEY,
    )

    # Store settings on app state for the router to use
    class MockSettings:
        PHOTO_DIR = str(photo_dir)
        MAX_PHOTO_SIZE = 204800
        MAX_QUEUE_DEPTH = 50
        DISK_USAGE_THRESHOLD = 0.90

    application.state.settings = MockSettings()

    # Mount photo router
    verify_key_dep = None  # Not needed for upload tests
    application.include_router(photos.create_router(verify_key_dep), prefix="/api")

    # Initialize DB
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)
    application.state.engine = engine

    # Seed: hive + camera node
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test Hive", created_at=utc_now())
        session.add(hive)
        await session.commit()

        key_hash = bcrypt.hashpw(DEVICE_KEY.encode(), bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(
            device_id=DEVICE_ID,
            hive_id=1,
            api_key_hash=key_hash,
            created_at=utc_now(),
        )
        session.add(node)
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app_with_camera):
    transport = ASGITransport(app=app_with_camera)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _upload(
    client,
    *,
    device_id=DEVICE_ID,
    device_key=DEVICE_KEY,
    hive_id=1,
    sequence=1,
    boot_id=100,
    data=None,
    captured_at="",
    captured_at_source="",
):
    """Helper to upload a photo."""
    if data is None:
        data = JPEG_HEADER
    return await client.post(
        "/api/photos/upload",
        headers={"X-Device-Id": device_id, "X-API-Key": device_key},
        files={"photo": ("test.jpg", data, "image/jpeg")},
        data={
            "hive_id": str(hive_id),
            "sequence": str(sequence),
            "boot_id": str(boot_id),
            "captured_at": captured_at,
            "captured_at_source": captured_at_source,
        },
    )


async def test_photo_upload_valid(client):
    resp = await _upload(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "photo_id" in body
    assert body["status"] == "queued"


async def test_photo_upload_not_jpeg(client):
    resp = await _upload(client, data=b"\x89PNG\r\n" + b"\x00" * 100)
    assert resp.status_code == 400


async def test_photo_upload_oversized(client, app_with_camera):
    app_with_camera.state.settings.MAX_PHOTO_SIZE = 100
    resp = await _upload(client, data=JPEG_HEADER + b"\x00" * 200)  # > 100 bytes
    assert resp.status_code == 400


async def test_photo_upload_wrong_hive(client):
    resp = await _upload(client, hive_id=2)
    assert resp.status_code == 400


async def test_photo_upload_unregistered_device(client):
    resp = await _upload(client, device_id="cam-unknown")
    assert resp.status_code == 404


async def test_photo_upload_wrong_key(client):
    resp = await _upload(client, device_key="wrong-key-" + "x" * 22)
    assert resp.status_code == 401


async def test_photo_upload_idempotent(client):
    resp1 = await _upload(client, sequence=42, boot_id=1)
    assert resp1.status_code == 200
    photo_id = resp1.json()["photo_id"]

    resp2 = await _upload(client, sequence=42, boot_id=1)
    assert resp2.status_code == 200
    assert resp2.json()["photo_id"] == photo_id
    assert resp2.json()["status"] == "duplicate"


async def test_photo_upload_sentinel_missing(client, app_with_camera):
    sentinel = os.path.join(app_with_camera.state.settings.PHOTO_DIR, ".waggle-sentinel")
    os.unlink(sentinel)
    resp = await _upload(client, sequence=99)
    assert resp.status_code == 503


async def test_photo_upload_queue_full(client, app_with_camera):
    app_with_camera.state.settings.MAX_QUEUE_DEPTH = 2
    # Upload 2 photos to fill queue
    await _upload(client, sequence=1, boot_id=200)
    await _upload(client, sequence=2, boot_id=200)
    # Third should be rejected
    resp = await _upload(client, sequence=3, boot_id=200)
    assert resp.status_code == 429


async def test_photo_upload_no_auth(client):
    resp = await client.post(
        "/api/photos/upload",
        files={"photo": ("test.jpg", JPEG_HEADER, "image/jpeg")},
        data={"hive_id": "1", "sequence": "1", "boot_id": "1"},
    )
    assert resp.status_code == 401


async def test_photo_upload_normalizes_captured_at(client, app_with_camera):
    """When captured_at is empty, should use ingested_at."""
    resp = await _upload(client, captured_at="", captured_at_source="", sequence=50, boot_id=300)
    assert resp.status_code == 200
    # Verify the photo was stored with captured_at_source = 'ingested'
    async with AsyncSession(app_with_camera.state.engine) as session:
        photo = (
            await session.execute(
                select(Photo).where(Photo.sequence == 50, Photo.boot_id == 300)
            )
        ).scalar_one()
        assert photo.captured_at_source == "ingested"
