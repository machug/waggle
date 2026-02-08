"""Sync status observability router."""

from fastapi import APIRouter, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import (
    Alert,
    BeeCount,
    CameraNode,
    Hive,
    Inspection,
    MlDetection,
    Photo,
    SensorReading,
    SyncState,
)
from waggle.schemas import SyncStatusOut


def create_router(verify_key) -> APIRouter:
    router = APIRouter(dependencies=[verify_key])

    @router.get("/sync/status")
    async def sync_status(request: Request):
        async with AsyncSession(request.app.state.engine) as session:
            # Get timestamps from sync_state
            async def _get_sync_state(key: str) -> str | None:
                result = await session.execute(
                    select(SyncState.value).where(SyncState.key == key)
                )
                return result.scalar_one_or_none()

            last_push_at = await _get_sync_state("last_push_at")
            last_pull_inspections_at = await _get_sync_state(
                "last_pull_inspections_at"
            )
            last_pull_alerts_at = await _get_sync_state("last_pull_alerts_at")

            # Count pending rows across all synced tables
            tables_with_sync = [
                Hive,
                SensorReading,
                BeeCount,
                Photo,
                MlDetection,
                CameraNode,
                Inspection,
                Alert,
            ]
            pending_rows = 0
            for model in tables_with_sync:
                count = (
                    await session.execute(
                        select(func.count())
                        .select_from(model)
                        .where(model.row_synced == 0)
                    )
                ).scalar()
                pending_rows += count or 0

            # Count pending files
            pending_files = (
                await session.execute(
                    select(func.count())
                    .select_from(Photo)
                    .where(Photo.file_synced == 0)
                )
            ).scalar() or 0

            return SyncStatusOut(
                last_push_at=last_push_at,
                last_pull_inspections_at=last_pull_inspections_at,
                last_pull_alerts_at=last_pull_alerts_at,
                pending_rows=pending_rows,
                pending_files=pending_files,
            )

    return router
