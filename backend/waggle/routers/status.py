"""Hub status endpoint returning system health information."""

import shutil
import time
from datetime import UTC

from fastapi import APIRouter, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive, SensorReading
from waggle.schemas import HubStatusOut, ServiceHealth

_START_TIME = time.monotonic()


def create_router():
    router = APIRouter(tags=["status"])

    @router.get("/hub/status", response_model=HubStatusOut)
    async def hub_status(request: Request):
        engine = request.app.state.engine

        async with AsyncSession(engine) as session:
            # Last ingested reading
            result = await session.execute(
                select(SensorReading.ingested_at)
                .order_by(desc(SensorReading.ingested_at))
                .limit(1)
            )
            last_ingest = result.scalar_one_or_none()

            # Hive count
            result = await session.execute(select(func.count()).select_from(Hive))
            hive_count = result.scalar_one()

            # Readings in last 24 hours
            from datetime import datetime, timedelta

            cutoff = (datetime.now(UTC) - timedelta(hours=24)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3] + "Z"
            result = await session.execute(
                select(func.count())
                .select_from(SensorReading)
                .where(SensorReading.ingested_at >= cutoff)
            )
            reading_count_24h = result.scalar_one()

        # Uptime
        uptime_sec = int(time.monotonic() - _START_TIME)

        # Disk free
        usage = shutil.disk_usage("/")
        disk_free_mb = usage.free // (1024 * 1024)

        # Services (static for now)
        services = ServiceHealth(bridge="ok", worker="ok", mqtt="ok", api="ok")

        # Overall status: ok if all services healthy
        all_ok = all(
            v == "ok"
            for v in [services.bridge, services.worker, services.mqtt, services.api]
        )
        status = "ok" if all_ok else "degraded"

        return HubStatusOut(
            status=status,
            uptime_sec=uptime_sec,
            last_ingest_at=last_ingest,
            mqtt_connected=True,
            disk_free_mb=disk_free_mb,
            hive_count=hive_count,
            reading_count_24h=reading_count_24h,
            services=services,
        )

    return router
