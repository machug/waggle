"""Readings router with raw/hourly/daily aggregation."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive, SensorReading
from waggle.schemas import AggregatedReading, ReadingOut, ReadingsResponse


async def _verify_hive_exists(session: AsyncSession, hive_id: int) -> None:
    """Raise 404 if the hive does not exist."""
    stmt = select(func.count()).select_from(Hive).where(Hive.id == hive_id)
    count = (await session.execute(stmt)).scalar_one()
    if count == 0:
        raise HTTPException(status_code=404, detail="Hive not found")


def _reading_out(row: SensorReading) -> ReadingOut:
    """Convert a SensorReading ORM instance to a ReadingOut schema."""
    return ReadingOut(
        id=row.id,
        hive_id=row.hive_id,
        observed_at=row.observed_at,
        weight_kg=row.weight_kg,
        temp_c=row.temp_c,
        humidity_pct=row.humidity_pct,
        pressure_hpa=row.pressure_hpa,
        battery_v=row.battery_v,
        sequence=row.sequence,
        flags=row.flags,
    )


def create_router(verify_key):
    router = APIRouter(tags=["readings"], dependencies=[verify_key])

    @router.get("/hives/{hive_id}/readings", response_model=ReadingsResponse)
    async def list_readings(
        hive_id: int,
        request: Request,
        interval: Literal["raw", "hourly", "daily"] = Query(default="raw"),
        start: str | None = Query(default=None),
        end: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            await _verify_hive_exists(session, hive_id)

            if interval == "raw":
                return await _raw_readings(
                    session, hive_id, start, end, limit, offset
                )
            else:
                return await _aggregated_readings(
                    session, hive_id, interval, start, end, limit, offset
                )

    @router.get("/hives/{hive_id}/readings/latest", response_model=ReadingOut)
    async def latest_reading(hive_id: int, request: Request):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            await _verify_hive_exists(session, hive_id)

            stmt = (
                select(SensorReading)
                .where(SensorReading.hive_id == hive_id)
                .order_by(desc(SensorReading.observed_at))
                .limit(1)
            )
            result = await session.execute(stmt)
            reading = result.scalar_one_or_none()
            if reading is None:
                raise HTTPException(status_code=404, detail="No readings found")
            return _reading_out(reading)

    return router


async def _raw_readings(
    session: AsyncSession,
    hive_id: int,
    start: str | None,
    end: str | None,
    limit: int,
    offset: int,
) -> ReadingsResponse:
    """Return individual readings ordered by observed_at DESC."""
    base = select(SensorReading).where(SensorReading.hive_id == hive_id)
    count_base = (
        select(func.count())
        .select_from(SensorReading)
        .where(SensorReading.hive_id == hive_id)
    )

    if start is not None:
        base = base.where(SensorReading.observed_at >= start)
        count_base = count_base.where(SensorReading.observed_at >= start)
    if end is not None:
        base = base.where(SensorReading.observed_at <= end)
        count_base = count_base.where(SensorReading.observed_at <= end)

    total = (await session.execute(count_base)).scalar_one()

    stmt = base.order_by(desc(SensorReading.observed_at)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    items = [_reading_out(r) for r in rows]
    return ReadingsResponse(
        items=items, interval="raw", total=total, limit=limit, offset=offset
    )


async def _aggregated_readings(
    session: AsyncSession,
    hive_id: int,
    interval: Literal["hourly", "daily"],
    start: str | None,
    end: str | None,
    limit: int,
    offset: int,
) -> ReadingsResponse:
    """Return aggregated readings grouped by hour or day."""
    if interval == "hourly":
        substr_len = 13  # YYYY-MM-DDTHH
        period_start_suffix = ":00:00.000Z"
        period_end_suffix = ":59:59.999Z"
    else:  # daily
        substr_len = 10  # YYYY-MM-DD
        period_start_suffix = "T00:00:00.000Z"
        period_end_suffix = "T23:59:59.999Z"

    group_expr = func.substr(SensorReading.observed_at, 1, substr_len)

    # Build WHERE conditions
    conditions = [SensorReading.hive_id == hive_id]
    if start is not None:
        conditions.append(SensorReading.observed_at >= start)
    if end is not None:
        conditions.append(SensorReading.observed_at <= end)

    # Count total distinct groups
    count_stmt = (
        select(func.count(func.distinct(group_expr)))
        .select_from(SensorReading)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Aggregation query
    period_start_col = (group_expr + period_start_suffix).label("period_start")
    period_end_col = (group_expr + period_end_suffix).label("period_end")

    stmt = (
        select(
            period_start_col,
            period_end_col,
            func.count().label("count"),
            func.avg(SensorReading.weight_kg).label("avg_weight_kg"),
            func.min(SensorReading.weight_kg).label("min_weight_kg"),
            func.max(SensorReading.weight_kg).label("max_weight_kg"),
            func.avg(SensorReading.temp_c).label("avg_temp_c"),
            func.min(SensorReading.temp_c).label("min_temp_c"),
            func.max(SensorReading.temp_c).label("max_temp_c"),
            func.avg(SensorReading.humidity_pct).label("avg_humidity_pct"),
            func.min(SensorReading.humidity_pct).label("min_humidity_pct"),
            func.max(SensorReading.humidity_pct).label("max_humidity_pct"),
            func.avg(SensorReading.pressure_hpa).label("avg_pressure_hpa"),
            func.min(SensorReading.pressure_hpa).label("min_pressure_hpa"),
            func.max(SensorReading.pressure_hpa).label("max_pressure_hpa"),
            func.avg(SensorReading.battery_v).label("avg_battery_v"),
            func.min(SensorReading.battery_v).label("min_battery_v"),
            func.max(SensorReading.battery_v).label("max_battery_v"),
        )
        .where(*conditions)
        .group_by(group_expr)
        .order_by(desc("period_start"))
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(stmt)
    rows = result.all()

    items = [
        AggregatedReading(
            period_start=row.period_start,
            period_end=row.period_end,
            count=row.count,
            avg_weight_kg=row.avg_weight_kg,
            min_weight_kg=row.min_weight_kg,
            max_weight_kg=row.max_weight_kg,
            avg_temp_c=row.avg_temp_c,
            min_temp_c=row.min_temp_c,
            max_temp_c=row.max_temp_c,
            avg_humidity_pct=row.avg_humidity_pct,
            min_humidity_pct=row.min_humidity_pct,
            max_humidity_pct=row.max_humidity_pct,
            avg_pressure_hpa=row.avg_pressure_hpa,
            min_pressure_hpa=row.min_pressure_hpa,
            max_pressure_hpa=row.max_pressure_hpa,
            avg_battery_v=row.avg_battery_v,
            min_battery_v=row.min_battery_v,
            max_battery_v=row.max_battery_v,
        )
        for row in rows
    ]

    return ReadingsResponse(
        items=items, interval=interval, total=total, limit=limit, offset=offset
    )
