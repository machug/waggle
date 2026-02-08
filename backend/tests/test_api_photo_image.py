"""Tests for photo image serving endpoint."""

import hashlib
import hmac
import os
import time

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import CameraNode, Hive, Photo
from waggle.routers import photos
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key"
SIGNING_SECRET = "test-signing-secret"
DEVICE_KEY = "a" * 32
JPEG_DATA = b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture
async def app_with_photo(tmp_path):
    db_path = tmp_path / "test.db"
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / ".waggle-sentinel").write_text("sentinel")

    application = create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key=API_KEY,
    )

    class MockSettings:
        PHOTO_DIR = str(photo_dir)
        MAX_PHOTO_SIZE = 204800
        MAX_QUEUE_DEPTH = 50
        DISK_USAGE_THRESHOLD = 0.90
        LOCAL_SIGNING_SECRET = SIGNING_SECRET
        LOCAL_SIGNING_TTL_SEC = 600

    application.state.settings = MockSettings()

    verify_key_dep = None  # Not used for these tests
    application.include_router(photos.create_router(verify_key_dep), prefix="/api")

    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)
    application.state.engine = engine

    # Seed hive + camera node + photo on disk
    async with AsyncSession(engine) as session:
        now = utc_now()
        hive = Hive(id=1, name="Test Hive", created_at=now)
        session.add(hive)
        await session.commit()

        key_hash = bcrypt.hashpw(DEVICE_KEY.encode(), bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(
            device_id="cam-1", hive_id=1, api_key_hash=key_hash, created_at=now
        )
        session.add(node)
        await session.commit()

        # Create photo file on disk
        relative_path = "1/2026-02-08/cam-1_100_1_test.jpg"
        full_dir = photo_dir / "1" / "2026-02-08"
        full_dir.mkdir(parents=True)
        (full_dir / "cam-1_100_1_test.jpg").write_bytes(JPEG_DATA)

        photo = Photo(
            hive_id=1,
            device_id="cam-1",
            boot_id=100,
            captured_at="2026-02-08T12:00:00.000Z",
            captured_at_source="device_ntp",
            ingested_at=now,
            sequence=1,
            photo_path=relative_path,
            file_size_bytes=len(JPEG_DATA),
            sha256=hashlib.sha256(JPEG_DATA).hexdigest(),
        )
        session.add(photo)
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app_with_photo):
    transport = ASGITransport(app=app_with_photo)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _sign_token(photo_id: int, expires: int, secret: str = SIGNING_SECRET) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        f"{photo_id}.{expires}".encode(),
        hashlib.sha256,
    ).hexdigest()


async def test_serve_photo_with_api_key(client):
    resp = await client.get("/api/photos/1/image", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert "private" in resp.headers.get("cache-control", "")
    assert resp.content[:3] == b"\xff\xd8\xff"


async def test_serve_photo_with_signed_token(client):
    expires = int(time.time()) + 600
    token = _sign_token(1, expires)
    resp = await client.get(f"/api/photos/1/image?token={token}&expires={expires}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


async def test_serve_photo_expired_token(client):
    expires = int(time.time()) - 100  # Expired
    token = _sign_token(1, expires)
    resp = await client.get(f"/api/photos/1/image?token={token}&expires={expires}")
    assert resp.status_code == 403


async def test_serve_photo_invalid_token(client):
    expires = int(time.time()) + 600
    resp = await client.get(f"/api/photos/1/image?token=badtoken&expires={expires}")
    assert resp.status_code == 403


async def test_serve_photo_no_auth(client):
    resp = await client.get("/api/photos/1/image")
    assert resp.status_code == 401


async def test_serve_photo_not_found(client):
    resp = await client.get("/api/photos/999/image", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 404


async def test_serve_photo_sentinel_missing(client, app_with_photo):
    sentinel = os.path.join(app_with_photo.state.settings.PHOTO_DIR, ".waggle-sentinel")
    os.unlink(sentinel)
    resp = await client.get("/api/photos/1/image", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 503
