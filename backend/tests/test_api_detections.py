"""Tests for ML detection list endpoint."""

import json

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.auth import create_api_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import CameraNode, Hive, MlDetection, Photo
from waggle.routers import detections
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key"


@pytest.fixture
async def app_with_detections(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)

    application = create_app(db_url=f"sqlite+aiosqlite:///{db_path}", api_key=API_KEY)
    application.state.engine = engine

    verify_key = create_api_key_dependency(API_KEY)
    application.include_router(detections.create_router(verify_key), prefix="/api")

    # Seed data
    async with AsyncSession(engine) as session:
        now = utc_now()
        hive = Hive(id=1, name="Test Hive", created_at=now)
        session.add(hive)
        await session.commit()

        key_hash = bcrypt.hashpw(b"a" * 32, bcrypt.gensalt(rounds=4)).decode()
        node = CameraNode(device_id="cam-1", hive_id=1, api_key_hash=key_hash, created_at=now)
        session.add(node)
        await session.commit()

        photo = Photo(
            hive_id=1,
            device_id="cam-1",
            boot_id=1,
            captured_at=now,
            captured_at_source="device_ntp",
            ingested_at=now,
            sequence=1,
            photo_path="1/test.jpg",
            file_size_bytes=1000,
            sha256="abc123",
        )
        session.add(photo)
        await session.commit()
        await session.refresh(photo)

        det = MlDetection(
            photo_id=photo.id,
            hive_id=1,
            detected_at=now,
            top_class="varroa",
            top_confidence=0.95,
            detections_json=json.dumps([{"class": "varroa", "confidence": 0.95}]),
            varroa_count=3,
            pollen_count=0,
            wasp_count=0,
            bee_count=12,
            inference_ms=150,
            model_version="yolov8n-waggle-v1",
            model_hash="abc",
        )
        session.add(det)
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app_with_detections):
    transport = ASGITransport(app=app_with_detections)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_list_detections(client):
    resp = await client.get(
        "/api/hives/1/detections",
        headers={"X-API-Key": API_KEY},
        params={"from": "2020-01-01T00:00:00.000Z", "to": "2030-01-01T00:00:00.000Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    d = data["items"][0]
    assert d["top_class"] == "varroa"
    assert d["varroa_count"] == 3
    assert isinstance(d["detections_json"], list)


async def test_list_detections_invalid_hive(client):
    resp = await client.get(
        "/api/hives/999/detections",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 404


async def test_list_detections_class_filter(client):
    resp = await client.get(
        "/api/hives/1/detections",
        headers={"X-API-Key": API_KEY},
        params={
            "class": "pollen",
            "from": "2020-01-01T00:00:00.000Z",
            "to": "2030-01-01T00:00:00.000Z",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0  # Only varroa detection exists


async def test_list_detections_confidence_filter(client):
    resp = await client.get(
        "/api/hives/1/detections",
        headers={"X-API-Key": API_KEY},
        params={
            "min_confidence": "0.99",
            "from": "2020-01-01T00:00:00.000Z",
            "to": "2030-01-01T00:00:00.000Z",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0  # Confidence is 0.95, below 0.99


async def test_list_detections_no_auth(client):
    resp = await client.get("/api/hives/1/detections")
    assert resp.status_code == 401
