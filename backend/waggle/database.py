"""Database engine creation with SQLite WAL mode and PRAGMA configuration."""

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from waggle.models import Base


def _set_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.close()


def create_engine_from_url(url: str, *, is_worker: bool = False) -> AsyncEngine:
    kwargs = {}
    if is_worker:
        kwargs["poolclass"] = StaticPool
    engine = create_async_engine(url, **kwargs)
    event.listen(engine.sync_engine, "connect", _set_pragmas)
    return engine


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
