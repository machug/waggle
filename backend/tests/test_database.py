"""Tests for database engine creation and WAL mode."""

import pytest
from sqlalchemy import text

from waggle.database import create_engine_from_url, init_db


@pytest.fixture
async def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(url, is_worker=False)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def worker_engine(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(url, is_worker=True)
    yield engine
    await engine.dispose()


async def test_wal_mode(db_engine):
    """Database should be in WAL journal mode."""
    async with db_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA journal_mode"))
        mode = result.scalar()
        assert mode == "wal"


async def test_foreign_keys_enabled(db_engine):
    """Foreign keys should be enforced."""
    async with db_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA foreign_keys"))
        assert result.scalar() == 1


async def test_busy_timeout_set(db_engine):
    """Busy timeout should be 30 seconds."""
    async with db_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA busy_timeout"))
        assert result.scalar() == 30000


async def test_init_db_creates_tables(tmp_path):
    """init_db should create all tables."""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine_from_url(url, is_worker=False)
    await init_db(engine)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = [row[0] for row in result.fetchall()]
    await engine.dispose()
    assert "hives" in tables
    assert "sensor_readings" in tables
    assert "alerts" in tables
