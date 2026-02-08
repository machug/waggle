"""Tests for varroa mite load endpoints."""

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.auth import create_api_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import CameraNode, Hive, MlDetection, Photo
from waggle.routers import varroa
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key"


@pytest.fixture
async def app_with_varroa_data(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)

    application = create_app(db_url=f"sqlite+aiosqlite:///{db_path}", api_key=API_KEY)
    application.state.engine = engine

    verify_key = create_api_key_dependency(API_KEY)
    application.include_router(varroa.create_router(verify_key), prefix="/api")

    now = utc_now()
    async with AsyncSession(engine) as session:
        hive = Hive(id=1, name="Test Hive", created_at=now)
        session.add(hive)
        await session.commit()

        key_hash = bcrypt.hashpw(b"a" * 32, bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(device_id="cam-1", hive_id=1, api_key_hash=key_hash, created_at=now)
        session.add(node)
        await session.commit()

        # Create photos and detections for today
        photo = Photo(
            hive_id=1, device_id="cam-1", boot_id=1,
            captured_at=now, captured_at_source="device_ntp",
            ingested_at=now, sequence=1, photo_path="1/test.jpg",
            file_size_bytes=1000, sha256="abc",
        )
        session.add(photo)
        await session.commit()
        await session.refresh(photo)

        det = MlDetection(
            photo_id=photo.id, hive_id=1, detected_at=now,
            top_class="varroa", top_confidence=0.9,
            detections_json="[]",
            varroa_count=5, pollen_count=0, wasp_count=0, bee_count=100,
            inference_ms=100, model_version="v1", model_hash="abc",
        )
        session.add(det)
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app_with_varroa_data):
    transport = ASGITransport(app=app_with_varroa_data)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_varroa_daily(client):
    resp = await client.get(
        "/api/hives/1/varroa",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "summary" in data
    assert len(data["items"]) >= 1
    day = data["items"][0]
    assert day["total_mites"] == 5
    assert day["total_bees"] == 100
    assert day["mites_per_100_bees"] == 5.0


async def test_varroa_invalid_hive(client):
    resp = await client.get(
        "/api/hives/999/varroa",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 404


async def test_varroa_overview(client):
    resp = await client.get(
        "/api/varroa/overview",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "hives" in data
    assert len(data["hives"]) >= 1
    assert data["hives"][0]["hive_id"] == 1
    assert data["hives"][0]["hive_name"] == "Test Hive"


async def test_varroa_no_auth(client):
    resp = await client.get("/api/hives/1/varroa")
    assert resp.status_code == 401


async def test_varroa_summary_trend(client):
    resp = await client.get(
        "/api/hives/1/varroa",
        headers={"X-API-Key": API_KEY},
    )
    data = resp.json()
    summary = data["summary"]
    # Only 1 day of data -> insufficient_data
    assert summary["trend_7d"] == "insufficient_data"
    assert summary["current_ratio"] == 5.0
