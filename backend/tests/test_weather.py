"""Tests for weather endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from waggle.auth import create_api_key_dependency
from waggle.database import create_engine_from_url, init_db
from waggle.main import create_app
from waggle.routers import weather

API_KEY = "test-api-key"


@pytest.fixture
async def app_none_provider(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)

    application = create_app(db_url=f"sqlite+aiosqlite:///{db_path}", api_key=API_KEY)
    application.state.engine = engine

    class MockSettings:
        WEATHER_PROVIDER = "none"

    application.state.settings = MockSettings()

    verify_key = create_api_key_dependency(API_KEY)
    application.include_router(weather.create_router(verify_key), prefix="/api")
    return application


@pytest.fixture
async def client_none(app_none_provider):
    transport = ASGITransport(app=app_none_provider)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_weather_none_provider(client_none):
    resp = await client_none.get(
        "/api/weather/current",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 503


async def test_weather_no_auth(client_none):
    resp = await client_none.get("/api/weather/current")
    assert resp.status_code == 401


@pytest.fixture
async def app_bom_provider(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite+aiosqlite:///{db_path}", is_worker=False)
    await init_db(engine)

    application = create_app(db_url=f"sqlite+aiosqlite:///{db_path}", api_key=API_KEY)
    application.state.engine = engine

    # Reset cache between tests
    weather._weather_cache["data"] = None
    weather._weather_cache["fetched_at"] = 0

    class MockSettings:
        WEATHER_PROVIDER = "bom"
        WEATHER_LATITUDE = "-33.8688"
        WEATHER_LONGITUDE = "151.2093"

    application.state.settings = MockSettings()

    verify_key = create_api_key_dependency(API_KEY)
    application.include_router(weather.create_router(verify_key), prefix="/api")
    return application


@pytest.fixture
async def client_bom(app_bom_provider):
    transport = ASGITransport(app=app_bom_provider)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_weather_bom_provider(client_bom):
    resp = await client_bom.get(
        "/api/weather/current",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "bom"
    assert data["fetched_at"] is not None
