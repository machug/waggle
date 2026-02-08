"""Traffic (bee counting) API endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive
from waggle.schemas import (
    TrafficAggregateOut,
    TrafficRecordOut,
    TrafficResponse,
    TrafficSummaryOut,
)


def create_router(verify_key):
    router = APIRouter(tags=["traffic"], dependencies=[verify_key])

    @router.get("/hives/{hive_id}/traffic", response_model=TrafficResponse)
    async def get_traffic(
        hive_id: int,
        request: Request,
        interval: str = Query(default="raw", pattern="^(raw|hourly|daily)$"),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        order: str = Query(default="desc", pattern="^(asc|desc)$"),
        from_time: str | None = Query(default=None, alias="from"),
        to_time: str | None = Query(default=None, alias="to"),
    ):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            await _get_hive_or_404(session, hive_id)

            if interval == "raw":
                return await _raw_traffic(
                    session, hive_id, from_time, to_time, order, limit, offset
                )
            else:
                return await _aggregated_traffic(
                    session, hive_id, interval, from_time, to_time, order, limit, offset
                )

    @router.get("/hives/{hive_id}/traffic/latest", response_model=TrafficRecordOut)
    async def get_traffic_latest(hive_id: int, request: Request):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            await _get_hive_or_404(session, hive_id)
            result = await session.execute(
                text(
                    "SELECT id, reading_id, hive_id, observed_at, period_ms, "
                    "bees_in, bees_out, net_out, total_traffic, lane_mask, stuck_mask, flags "
                    "FROM bee_counts WHERE hive_id = :hive_id "
                    "ORDER BY observed_at DESC LIMIT 1"
                ),
                {"hive_id": hive_id},
            )
            row = result.first()
            if row is None:
                raise HTTPException(404, "No traffic data for this hive")
            return TrafficRecordOut(**dict(row._mapping))

    @router.get("/hives/{hive_id}/traffic/summary", response_model=TrafficSummaryOut)
    async def get_traffic_summary(
        hive_id: int,
        request: Request,
        date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            await _get_hive_or_404(session, hive_id)

            target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")

            # Daily totals
            result = await session.execute(
                text(
                    "SELECT COALESCE(SUM(bees_in), 0) AS total_in, "
                    "COALESCE(SUM(bees_out), 0) AS total_out, "
                    "COALESCE(SUM(net_out), 0) AS net_out, "
                    "COALESCE(SUM(total_traffic), 0) AS total_traffic "
                    "FROM bee_counts "
                    "WHERE hive_id = :hive_id AND substr(observed_at, 1, 10) = :date"
                ),
                {"hive_id": hive_id, "date": target_date},
            )
            row = result.first()
            total_in = row.total_in
            total_out = row.total_out
            net_out = row.net_out
            total_traffic = row.total_traffic

            # Peak hour
            result = await session.execute(
                text(
                    "SELECT CAST(substr(observed_at, 12, 2) AS INTEGER) AS hr, "
                    "SUM(total_traffic) AS hour_traffic "
                    "FROM bee_counts "
                    "WHERE hive_id = :hive_id AND substr(observed_at, 1, 10) = :date "
                    "GROUP BY hr ORDER BY hour_traffic DESC LIMIT 1"
                ),
                {"hive_id": hive_id, "date": target_date},
            )
            peak_row = result.first()
            peak_hour = (
                peak_row.hr if peak_row and peak_row.hour_traffic > 0 else None
            )

            # 7-day rolling avg
            result = await session.execute(
                text(
                    "SELECT substr(observed_at, 1, 10) AS day, "
                    "SUM(total_traffic) AS day_total "
                    "FROM bee_counts "
                    "WHERE hive_id = :hive_id "
                    "AND substr(observed_at, 1, 10) < :date "
                    "AND substr(observed_at, 1, 10) >= :start_date "
                    "GROUP BY day ORDER BY day"
                ),
                {
                    "hive_id": hive_id,
                    "date": target_date,
                    "start_date": (
                        datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=7)
                    ).strftime("%Y-%m-%d"),
                },
            )
            prior_days = result.all()

            if len(prior_days) >= 3:
                avg_total = sum(r.day_total for r in prior_days) // len(prior_days)
                activity_score = (
                    round(min(100, max(0, 100 * total_traffic / avg_total)))
                    if avg_total > 0
                    else 0
                )
            else:
                avg_total = None
                activity_score = None

            return TrafficSummaryOut(
                date=target_date,
                total_in=total_in,
                total_out=total_out,
                net_out=net_out,
                total_traffic=total_traffic,
                peak_hour=peak_hour,
                rolling_7d_avg_total=avg_total,
                activity_score=activity_score,
            )

    return router


async def _get_hive_or_404(session, hive_id):
    from sqlalchemy import select

    result = await session.execute(select(Hive).where(Hive.id == hive_id))
    hive = result.scalar_one_or_none()
    if hive is None:
        raise HTTPException(404, "Hive not found")
    return hive


async def _raw_traffic(session, hive_id, from_time, to_time, order, limit, offset):
    where_clauses = ["hive_id = :hive_id"]
    params = {"hive_id": hive_id}

    if from_time:
        where_clauses.append("observed_at >= :from_time")
        params["from_time"] = from_time
    if to_time:
        where_clauses.append("observed_at <= :to_time")
        params["to_time"] = to_time

    where_sql = " AND ".join(where_clauses)
    order_dir = "ASC" if order == "asc" else "DESC"

    # Total count
    count_result = await session.execute(
        text(f"SELECT COUNT(*) FROM bee_counts WHERE {where_sql}"), params
    )
    total = count_result.scalar()

    # Data
    result = await session.execute(
        text(
            f"SELECT id, reading_id, hive_id, observed_at, period_ms, "
            f"bees_in, bees_out, net_out, total_traffic, lane_mask, stuck_mask, flags "
            f"FROM bee_counts WHERE {where_sql} "
            f"ORDER BY observed_at {order_dir} LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    )

    items = [TrafficRecordOut(**dict(r._mapping)) for r in result]
    return TrafficResponse(
        items=items, interval="raw", total=total, limit=limit, offset=offset
    )


async def _aggregated_traffic(
    session, hive_id, interval, from_time, to_time, order, limit, offset
):
    if interval == "hourly":
        group_len = 13  # "2026-02-08T12"
        period_suffix_start = ":00:00.000Z"
        period_suffix_end = ":59:59.999Z"
    else:  # daily
        group_len = 10  # "2026-02-08"
        period_suffix_start = "T00:00:00.000Z"
        period_suffix_end = "T23:59:59.999Z"

    where_clauses = ["hive_id = :hive_id"]
    params = {"hive_id": hive_id}

    if from_time:
        where_clauses.append("observed_at >= :from_time")
        params["from_time"] = from_time
    if to_time:
        where_clauses.append("observed_at <= :to_time")
        params["to_time"] = to_time

    where_sql = " AND ".join(where_clauses)
    order_dir = "ASC" if order == "asc" else "DESC"

    # Count distinct periods
    count_result = await session.execute(
        text(
            f"SELECT COUNT(DISTINCT substr(observed_at, 1, {group_len})) "
            f"FROM bee_counts WHERE {where_sql}"
        ),
        params,
    )
    total = count_result.scalar()

    # Aggregated data with rate normalization
    result = await session.execute(
        text(
            f"SELECT substr(observed_at, 1, {group_len}) AS period, "
            f"COUNT(*) AS reading_count, "
            f"SUM(bees_in) AS sum_bees_in, SUM(bees_out) AS sum_bees_out, "
            f"SUM(net_out) AS sum_net_out, SUM(total_traffic) AS sum_total_traffic, "
            f"CASE WHEN SUM(period_ms) > 0 THEN SUM(bees_in) * 60000.0 / SUM(period_ms) ELSE 0.0 END AS avg_bees_in_per_min, "
            f"CASE WHEN SUM(period_ms) > 0 THEN SUM(bees_out) * 60000.0 / SUM(period_ms) ELSE 0.0 END AS avg_bees_out_per_min "
            f"FROM bee_counts WHERE {where_sql} "
            f"GROUP BY period ORDER BY period {order_dir} LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    )

    items = []
    for r in result:
        items.append(
            TrafficAggregateOut(
                period_start=r.period + period_suffix_start,
                period_end=r.period + period_suffix_end,
                reading_count=r.reading_count,
                sum_bees_in=r.sum_bees_in,
                sum_bees_out=r.sum_bees_out,
                sum_net_out=r.sum_net_out,
                sum_total_traffic=r.sum_total_traffic,
                avg_bees_in_per_min=round(r.avg_bees_in_per_min, 2),
                avg_bees_out_per_min=round(r.avg_bees_out_per_min, 2),
            )
        )

    return TrafficResponse(
        items=items, interval=interval, total=total, limit=limit, offset=offset
    )
