"""Hub status endpoint returning system health information."""

import shutil
import time
from datetime import UTC

from fastapi import APIRouter, Request
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import BeeCount, Hive, SensorReading
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

            # Traffic readings in last 24h
            result = await session.execute(
                select(func.count())
                .select_from(BeeCount)
                .where(BeeCount.ingested_at >= cutoff)
            )
            traffic_readings_24h = result.scalar_one()

            # Phase 2 nodes active (distinct hive_ids with bee_counts in 24h)
            result = await session.execute(
                select(func.count(func.distinct(BeeCount.hive_id))).where(
                    BeeCount.ingested_at >= cutoff
                )
            )
            phase2_nodes_active = result.scalar_one()

            # Stuck lanes - latest bee_count per hive, sum popcount of stuck_mask
            result = await session.execute(
                text(
                    "SELECT COALESCE(SUM("
                    "  (stuck_mask & 1) + ((stuck_mask >> 1) & 1) + "
                    "  ((stuck_mask >> 2) & 1) + ((stuck_mask >> 3) & 1) + "
                    "  ((stuck_mask >> 4) & 1) + ((stuck_mask >> 5) & 1) + "
                    "  ((stuck_mask >> 6) & 1) + ((stuck_mask >> 7) & 1)"
                    "), 0) "
                    "FROM (SELECT stuck_mask FROM bee_counts bc1 "
                    "WHERE bc1.observed_at = (SELECT MAX(bc2.observed_at) "
                    "FROM bee_counts bc2 "
                    "WHERE bc2.hive_id = bc1.hive_id))"
                )
            )
            stuck_lanes_total = result.scalar()

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
            traffic_readings_24h=traffic_readings_24h,
            phase2_nodes_active=phase2_nodes_active,
            stuck_lanes_total=stuck_lanes_total,
        )

    return router
