"""Tests for photo list endpoint."""

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.auth import create_api_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import CameraNode, Hive, Photo
from waggle.routers import photos
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key-for-photos"
DEVICE_ID = "cam-list-01"


@pytest.fixture
async def app_with_photos(tmp_path):
    """Create app with hive, camera node, and photo router with API key auth."""
    db_path = tmp_path / "test.db"
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / ".waggle-sentinel").write_text("waggle photo storage sentinel")

    application = create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key=API_KEY,
    )

    class MockSettings:
        PHOTO_DIR = str(photo_dir)
        MAX_PHOTO_SIZE = 204800
        MAX_QUEUE_DEPTH = 50
        DISK_USAGE_THRESHOLD = 0.90
        FASTAPI_BASE_URL = "http://192.168.1.50:8000"
        LOCAL_SIGNING_SECRET = "test-signing-secret"
        LOCAL_SIGNING_TTL_SEC = 600

    application.state.settings = MockSettings()

    # Mount photo router WITH verify_key for the list endpoint
    verify_key = create_api_key_dependency(API_KEY)
    application.include_router(photos.create_router(verify_key), prefix="/api")

    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)
    application.state.engine = engine

    # Seed: hive + camera node
    key_hash = bcrypt.hashpw(b"a" * 32, bcrypt.gensalt(rounds=4)).decode()
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test Hive", created_at=utc_now())
        session.add(hive)
        await session.commit()

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
async def client(app_with_photos):
    transport = ASGITransport(app=app_with_photos)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _insert_photo(engine, *, hive_id=1, device_id=DEVICE_ID, boot_id=1, sequence=1,
                         captured_at=None, ml_status="pending"):
    """Insert a Photo row directly into the DB."""
    now = utc_now()
    if captured_at is None:
        captured_at = now
    async with AsyncSession(engine) as session:
        photo = Photo(
            hive_id=hive_id,
            device_id=device_id,
            boot_id=boot_id,
            captured_at=captured_at,
            captured_at_source="device_ntp",
            ingested_at=now,
            sequence=sequence,
            photo_path=f"{hive_id}/2026-02-08/{device_id}_{boot_id}_{sequence}.jpg",
            file_size_bytes=1024,
            sha256="a" * 64,
            ml_status=ml_status,
        )
        session.add(photo)
        await session.commit()
        await session.refresh(photo)
        return photo.id


async def test_list_photos_empty(client):
    """Hive exists but has no photos -- should return empty items."""
    resp = await client.get(
        "/api/hives/1/photos",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 100
    assert body["offset"] == 0


async def test_list_photos_returns_photos(client, app_with_photos):
    """Insert a photo then list -- should return 1 item with signed URL."""
    photo_id = await _insert_photo(app_with_photos.state.engine)

    resp = await client.get(
        "/api/hives/1/photos",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["id"] == photo_id
    assert item["hive_id"] == 1
    assert item["device_id"] == DEVICE_ID
    assert item["ml_status"] == "pending"

    # Signed URL checks
    assert "local_image_url" in item
    url = item["local_image_url"]
    assert url.startswith("http://192.168.1.50:8000/api/photos/")
    assert "token=" in url
    assert "expires=" in url
    assert item["local_image_expires_at"] > 0


async def test_list_photos_invalid_hive(client):
    """Non-existent hive should return 404."""
    resp = await client.get(
        "/api/hives/999/photos",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 404


async def test_list_photos_ml_status_filter(client, app_with_photos):
    """Filter by ml_status=pending should only return pending photos."""
    engine = app_with_photos.state.engine
    await _insert_photo(engine, sequence=1, boot_id=10, ml_status="pending")
    await _insert_photo(engine, sequence=2, boot_id=10, ml_status="completed")

    resp = await client.get(
        "/api/hives/1/photos?ml_status=pending",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert all(item["ml_status"] == "pending" for item in body["items"])


async def test_list_photos_no_auth(client):
    """Request without API key should return 401."""
    resp = await client.get("/api/hives/1/photos")
    assert resp.status_code == 401
