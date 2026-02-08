"""Tests for Phase 3 hive detail updates (camera, photo, varroa fields)."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.models import Hive
from waggle.utils.timestamps import utc_now

API_KEY = "test-api-key"


@pytest.fixture
async def app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)
    application = create_app(db_url=f"sqlite+aiosqlite:///{db_path}", api_key=API_KEY)
    application.state.engine = engine

    # Seed a hive
    async with AsyncSession(engine) as session:
        session.add(Hive(id=1, name="Test Hive", created_at=utc_now()))
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_hive_detail_has_phase3_fields(client):
    """GET /api/hives/1 includes Phase 3 summary fields (all None for bare hive)."""
    resp = await client.get(
        "/api/hives/1",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "camera_node_id" in data
    assert "latest_photo_at" in data
    assert "latest_ml_status" in data
    assert "varroa_ratio" in data
    # All None for hive without camera/photos
    assert data["camera_node_id"] is None
    assert data["latest_photo_at"] is None
    assert data["latest_ml_status"] is None
    assert data["varroa_ratio"] is None


async def test_hive_list_has_phase3_fields(client):
    """GET /api/hives returns Phase 3 fields on each hive item."""
    resp = await client.get(
        "/api/hives",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1
    hive = data["items"][0]
    assert "camera_node_id" in hive
    assert "latest_photo_at" in hive
    assert "latest_ml_status" in hive
    assert "varroa_ratio" in hive


async def test_hive_detail_with_camera_node(app, client):
    """Hive detail shows camera_node_id when a camera node is registered."""
    engine = app.state.engine
    now = utc_now()
    async with AsyncSession(engine) as session:
        await session.execute(
            text(
                "INSERT INTO camera_nodes (device_id, hive_id, api_key_hash, created_at) "
                "VALUES (:did, :hid, :hash, :ts)"
            ),
            {"did": "cam-alpha", "hid": 1, "hash": "x" * 60, "ts": now},
        )
        await session.commit()

    resp = await client.get(
        "/api/hives/1",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_node_id"] == "cam-alpha"


async def test_hive_detail_with_photo(app, client):
    """Hive detail shows latest_photo_at and latest_ml_status when photos exist."""
    engine = app.state.engine
    now = utc_now()
    async with AsyncSession(engine) as session:
        # Camera node required for FK
        await session.execute(
            text(
                "INSERT INTO camera_nodes (device_id, hive_id, api_key_hash, created_at) "
                "VALUES (:did, :hid, :hash, :ts)"
            ),
            {"did": "cam-beta", "hid": 1, "hash": "y" * 60, "ts": now},
        )
        await session.execute(
            text(
                "INSERT INTO photos "
                "(hive_id, device_id, boot_id, captured_at, captured_at_source, "
                "sequence, photo_path, file_size_bytes, sha256, ml_status) "
                "VALUES (:hid, :did, :bid, :cap, :src, :seq, :path, :sz, :sha, :ml)"
            ),
            {
                "hid": 1,
                "did": "cam-beta",
                "bid": 1,
                "cap": now,
                "src": "device_ntp",
                "seq": 1,
                "path": "/photos/test.jpg",
                "sz": 12345,
                "sha": "a" * 64,
                "ml": "completed",
            },
        )
        await session.commit()

    resp = await client.get(
        "/api/hives/1",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_photo_at"] == now
    assert data["latest_ml_status"] == "completed"


async def test_hive_detail_with_varroa_ratio(app, client):
    """Hive detail shows varroa_ratio computed from recent ml_detections."""
    engine = app.state.engine
    now = utc_now()
    detected_at = now
    async with AsyncSession(engine) as session:
        # Camera node + photo required for FK chain
        await session.execute(
            text(
                "INSERT INTO camera_nodes (device_id, hive_id, api_key_hash, created_at) "
                "VALUES (:did, :hid, :hash, :ts)"
            ),
            {"did": "cam-gamma", "hid": 1, "hash": "z" * 60, "ts": now},
        )
        await session.execute(
            text(
                "INSERT INTO photos "
                "(id, hive_id, device_id, boot_id, captured_at, captured_at_source, "
                "sequence, photo_path, file_size_bytes, sha256, ml_status) "
                "VALUES (:pid, :hid, :did, :bid, :cap, :src, :seq, :path, :sz, :sha, :ml)"
            ),
            {
                "pid": 1,
                "hid": 1,
                "did": "cam-gamma",
                "bid": 1,
                "cap": now,
                "src": "device_ntp",
                "seq": 1,
                "path": "/photos/test2.jpg",
                "sz": 11111,
                "sha": "b" * 64,
                "ml": "completed",
            },
        )
        # Detection: 5 varroa out of 100 bees = 5.0 mites/100 bees
        await session.execute(
            text(
                "INSERT INTO ml_detections "
                "(photo_id, hive_id, detected_at, top_class, top_confidence, "
                "varroa_count, bee_count, inference_ms, model_hash) "
                "VALUES (:pid, :hid, :det, :tc, :conf, :vc, :bc, :ms, :mh)"
            ),
            {
                "pid": 1,
                "hid": 1,
                "det": detected_at,
                "tc": "varroa",
                "conf": 0.95,
                "vc": 5,
                "bc": 100,
                "ms": 150,
                "mh": "c" * 64,
            },
        )
        await session.commit()

    resp = await client.get(
        "/api/hives/1",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["varroa_ratio"] == 5.0


async def test_hive_list_with_phase3_data(app, client):
    """Hive list also populates Phase 3 fields when data exists."""
    engine = app.state.engine
    now = utc_now()
    async with AsyncSession(engine) as session:
        await session.execute(
            text(
                "INSERT INTO camera_nodes (device_id, hive_id, api_key_hash, created_at) "
                "VALUES (:did, :hid, :hash, :ts)"
            ),
            {"did": "cam-list", "hid": 1, "hash": "w" * 60, "ts": now},
        )
        await session.commit()

    resp = await client.get(
        "/api/hives",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    hive = data["items"][0]
    assert hive["camera_node_id"] == "cam-list"
