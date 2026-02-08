"""Cloud sync service — bidirectional sync between local SQLite and Supabase."""

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from waggle.models import (
    Alert,
    BeeCount,
    CameraNode,
    Hive,
    Inspection,
    MlDetection,
    Photo,
    SensorReading,
)

logger = logging.getLogger(__name__)

# FK dependency order for push sync
PUSH_ORDER = [
    ("hives", Hive),
    ("camera_nodes", CameraNode),
    ("sensor_readings", SensorReading),
    ("bee_counts", BeeCount),
    ("photos", Photo),
    ("ml_detections", MlDetection),
    ("alerts", Alert),
    ("inspections", Inspection),
]

BATCH_SIZE = 500


def _row_to_dict(row, table_name: str) -> dict:
    """Convert a SQLAlchemy model instance to a Supabase-compatible dict."""
    d = {}
    for col in row.__table__.columns:
        name = col.name
        # Skip local-only columns
        if name in ("row_synced", "file_synced"):
            continue
        val = getattr(row, name)
        # Convert SQLite INTEGER booleans to Python bools for Postgres BOOLEAN
        if name in ("acknowledged", "queen_seen"):
            val = bool(val) if val is not None else False
        d[name] = val
    return d


async def push_rows(engine: AsyncEngine, supabase_client) -> dict:
    """Push unsynced rows (row_synced=0) to Supabase in FK dependency order.

    For each table in PUSH_ORDER:
    1. Query rows where row_synced = 0, LIMIT BATCH_SIZE
    2. Convert each row to a Supabase-compatible dict
    3. Upsert to Supabase (inspections use RPC, others use table().upsert())
    4. On success, mark pushed rows as row_synced = 1
    5. On failure, log error and skip to next table

    Returns a summary dict: {"hives": 5, "sensor_readings": 100, ...}
    """
    summary = {}

    for table_name, model_cls in PUSH_ORDER:
        try:
            # Step 1: Query unsynced rows
            async with AsyncSession(engine) as session:
                stmt = select(model_cls).where(model_cls.row_synced == 0).limit(BATCH_SIZE)
                result = await session.execute(stmt)
                rows = result.scalars().all()

            if not rows:
                continue

            # Step 2: Convert to dicts
            rows_dicts = [_row_to_dict(row, table_name) for row in rows]

            # Step 3: Push to Supabase
            if table_name == "inspections":
                # Inspections use RPC for last-write-wins conflict resolution
                for row_dict in rows_dicts:
                    supabase_client.rpc("upsert_inspection_lww", row_dict)
            else:
                supabase_client.table(table_name).upsert(rows_dicts).execute()

            # Step 4: Mark as synced in a separate transaction
            pk_col = _get_pk_column(model_cls)
            pk_values = [getattr(row, pk_col) for row in rows]

            async with AsyncSession(engine) as session:
                async with session.begin():
                    # Use raw SQL update for efficiency
                    if len(pk_values) == 1:
                        await session.execute(
                            text(f"UPDATE {table_name} SET row_synced = 1 WHERE {pk_col} = :pk"),
                            {"pk": pk_values[0]},
                        )
                    else:
                        # Use IN clause for batch update
                        placeholders = ", ".join(f":pk{i}" for i in range(len(pk_values)))
                        params = {f"pk{i}": v for i, v in enumerate(pk_values)}
                        await session.execute(
                            text(
                                f"UPDATE {table_name} SET row_synced = 1 "
                                f"WHERE {pk_col} IN ({placeholders})"
                            ),
                            params,
                        )

            summary[table_name] = len(rows)
            logger.info("Pushed %d rows to %s", len(rows), table_name)

        except Exception:
            logger.exception("Failed to push %s to Supabase", table_name)
            # Skip to next table — don't mark as synced
            continue

    return summary


def _get_pk_column(model_cls) -> str:
    """Get the primary key column name for a model."""
    pk_cols = [col.name for col in model_cls.__table__.primary_key.columns]
    return pk_cols[0]
