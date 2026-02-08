"""Hives CRUD router."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import BeeCount, Hive, SensorReading
from waggle.schemas import HiveCreate, HiveOut, HivesResponse, HiveUpdate, LatestReading, LatestTrafficOut
from waggle.utils.timestamps import utc_now


def _hive_out(
    hive: Hive,
    latest: LatestReading | None = None,
    latest_traffic: LatestTrafficOut | None = None,
    activity_score_today: int | None = None,
) -> HiveOut:
    """Convert a Hive ORM instance to a HiveOut schema."""
    return HiveOut(
        id=hive.id,
        name=hive.name,
        location=hive.location,
        notes=hive.notes,
        sender_mac=hive.sender_mac,
        last_seen_at=hive.last_seen_at,
        created_at=hive.created_at,
        latest_reading=latest,
        latest_traffic=latest_traffic,
        activity_score_today=activity_score_today,
    )


def _latest_reading_from_row(row) -> LatestReading | None:
    """Build a LatestReading from a joined row, or None if no reading exists."""
    if row.observed_at is None:
        return None
    return LatestReading(
        weight_kg=row.weight_kg,
        temp_c=row.temp_c,
        humidity_pct=row.humidity_pct,
        pressure_hpa=row.pressure_hpa,
        battery_v=row.battery_v,
        observed_at=row.observed_at,
        flags=row.flags,
    )


def _latest_traffic_subquery():
    """Build a subquery for the most recent bee_count per hive."""
    return (
        select(
            BeeCount.hive_id,
            BeeCount.observed_at.label("bc_observed_at"),
            BeeCount.bees_in.label("bc_bees_in"),
            BeeCount.bees_out.label("bc_bees_out"),
            BeeCount.net_out.label("bc_net_out"),
            BeeCount.total_traffic.label("bc_total_traffic"),
            func.row_number()
            .over(
                partition_by=BeeCount.hive_id,
                order_by=desc(BeeCount.observed_at),
            )
            .label("bc_rn"),
        )
        .subquery()
    )


def _latest_traffic_from_row(bc_observed_at, bc_bees_in, bc_bees_out, bc_net_out, bc_total_traffic) -> LatestTrafficOut | None:
    """Build a LatestTrafficOut from joined columns, or None if no bee count exists."""
    if bc_observed_at is None:
        return None
    return LatestTrafficOut(
        observed_at=bc_observed_at,
        bees_in=bc_bees_in,
        bees_out=bc_bees_out,
        net_out=bc_net_out,
        total_traffic=bc_total_traffic,
    )


async def _compute_activity_scores(session, hive_ids: list[int]) -> dict[int, int | None]:
    """Compute activity_score_today for a set of hive IDs.

    activity_score = round(min(100, max(0, 100 * today_total / rolling_7d_avg)))
    Returns None if fewer than 3 prior days of data.
    """
    if not hive_ids:
        return {}

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Today's total traffic per hive
    today_result = await session.execute(
        text(
            "SELECT bc.hive_id, "
            "SUM(bc.total_traffic) AS today_total "
            "FROM bee_counts bc "
            "WHERE substr(bc.observed_at, 1, 10) = :today "
            "GROUP BY bc.hive_id"
        ),
        {"today": today},
    )
    today_totals: dict[int, int] = {row[0]: row[1] for row in today_result.all()}

    # Rolling 7-day average (excluding today) per hive
    avg_result = await session.execute(
        text(
            "SELECT hive_id, "
            "COUNT(DISTINCT substr(observed_at, 1, 10)) AS day_count, "
            "SUM(total_traffic) AS period_total "
            "FROM bee_counts "
            "WHERE substr(observed_at, 1, 10) >= :start "
            "AND substr(observed_at, 1, 10) < :today "
            "GROUP BY hive_id"
        ),
        {
            "start": (datetime.now(UTC).date() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "today": today,
        },
    )

    avg_data: dict[int, tuple[int, int]] = {
        row[0]: (row[1], row[2]) for row in avg_result.all()
    }

    scores: dict[int, int | None] = {}
    for hive_id in hive_ids:
        today_total = today_totals.get(hive_id)
        hist = avg_data.get(hive_id)

        if today_total is None or hist is None or hist[0] < 3:
            scores[hive_id] = None
            continue

        day_count, period_total = hist
        avg_daily = period_total / day_count
        if avg_daily == 0:
            scores[hive_id] = 100 if today_total > 0 else 0
        else:
            scores[hive_id] = round(min(100, max(0, 100 * today_total / avg_daily)))

    return scores


def create_router(verify_key):
    router = APIRouter(tags=["hives"], dependencies=[verify_key])

    @router.post("/hives", status_code=201, response_model=HiveOut)
    async def create_hive(body: HiveCreate, request: Request):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            hive = Hive(
                id=body.id,
                name=body.name,
                location=body.location,
                notes=body.notes,
                sender_mac=body.sender_mac,
                last_seen_at=None,
                created_at=utc_now(),
            )
            session.add(hive)
            try:
                await session.commit()
            except IntegrityError:
                raise HTTPException(
                    status_code=409,
                    detail="Hive with this id or name already exists",
                )
            await session.refresh(hive)
            return _hive_out(hive)

    @router.get("/hives", response_model=HivesResponse)
    async def list_hives(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            # Total count
            count_stmt = select(func.count()).select_from(Hive)
            total = (await session.execute(count_stmt)).scalar_one()

            # Latest reading subquery using row_number window function
            latest_subq = (
                select(
                    SensorReading.hive_id,
                    SensorReading.weight_kg,
                    SensorReading.temp_c,
                    SensorReading.humidity_pct,
                    SensorReading.pressure_hpa,
                    SensorReading.battery_v,
                    SensorReading.observed_at,
                    SensorReading.flags,
                    func.row_number()
                    .over(
                        partition_by=SensorReading.hive_id,
                        order_by=desc(SensorReading.observed_at),
                    )
                    .label("rn"),
                )
                .subquery()
            )

            # Latest traffic subquery
            traffic_subq = _latest_traffic_subquery()

            # Main query: hives left-joined with latest reading and latest traffic
            stmt = (
                select(
                    Hive,
                    latest_subq.c.weight_kg,
                    latest_subq.c.temp_c,
                    latest_subq.c.humidity_pct,
                    latest_subq.c.pressure_hpa,
                    latest_subq.c.battery_v,
                    latest_subq.c.observed_at,
                    latest_subq.c.flags,
                    traffic_subq.c.bc_observed_at,
                    traffic_subq.c.bc_bees_in,
                    traffic_subq.c.bc_bees_out,
                    traffic_subq.c.bc_net_out,
                    traffic_subq.c.bc_total_traffic,
                )
                .outerjoin(
                    latest_subq,
                    (Hive.id == latest_subq.c.hive_id) & (latest_subq.c.rn == 1),
                )
                .outerjoin(
                    traffic_subq,
                    (Hive.id == traffic_subq.c.hive_id) & (traffic_subq.c.bc_rn == 1),
                )
                .order_by(Hive.name.asc())
                .limit(limit)
                .offset(offset)
            )

            result = await session.execute(stmt)
            rows = result.all()

            # Collect hive IDs for activity score computation
            hive_ids = [row[0].id for row in rows]
            activity_scores = await _compute_activity_scores(session, hive_ids)

            items = []
            for row in rows:
                hive = row[0]
                # Build a namespace-like object for the reading columns
                class _ReadingRow:
                    pass
                r = _ReadingRow()
                r.weight_kg = row[1]
                r.temp_c = row[2]
                r.humidity_pct = row[3]
                r.pressure_hpa = row[4]
                r.battery_v = row[5]
                r.observed_at = row[6]
                r.flags = row[7]
                latest = _latest_reading_from_row(r)
                traffic = _latest_traffic_from_row(row[8], row[9], row[10], row[11], row[12])
                items.append(_hive_out(
                    hive, latest, traffic, activity_scores.get(hive.id),
                ))

            return HivesResponse(items=items, total=total, limit=limit, offset=offset)

    @router.get("/hives/{hive_id}", response_model=HiveOut)
    async def get_hive(hive_id: int, request: Request):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            # Latest reading subquery
            latest_subq = (
                select(
                    SensorReading.hive_id,
                    SensorReading.weight_kg,
                    SensorReading.temp_c,
                    SensorReading.humidity_pct,
                    SensorReading.pressure_hpa,
                    SensorReading.battery_v,
                    SensorReading.observed_at,
                    SensorReading.flags,
                    func.row_number()
                    .over(
                        partition_by=SensorReading.hive_id,
                        order_by=desc(SensorReading.observed_at),
                    )
                    .label("rn"),
                )
                .subquery()
            )

            # Latest traffic subquery
            traffic_subq = _latest_traffic_subquery()

            stmt = (
                select(
                    Hive,
                    latest_subq.c.weight_kg,
                    latest_subq.c.temp_c,
                    latest_subq.c.humidity_pct,
                    latest_subq.c.pressure_hpa,
                    latest_subq.c.battery_v,
                    latest_subq.c.observed_at,
                    latest_subq.c.flags,
                    traffic_subq.c.bc_observed_at,
                    traffic_subq.c.bc_bees_in,
                    traffic_subq.c.bc_bees_out,
                    traffic_subq.c.bc_net_out,
                    traffic_subq.c.bc_total_traffic,
                )
                .outerjoin(
                    latest_subq,
                    (Hive.id == latest_subq.c.hive_id) & (latest_subq.c.rn == 1),
                )
                .outerjoin(
                    traffic_subq,
                    (Hive.id == traffic_subq.c.hive_id) & (traffic_subq.c.bc_rn == 1),
                )
                .where(Hive.id == hive_id)
            )

            result = await session.execute(stmt)
            row = result.first()
            if row is None:
                raise HTTPException(status_code=404, detail="Hive not found")

            hive = row[0]
            class _ReadingRow:
                pass
            r = _ReadingRow()
            r.weight_kg = row[1]
            r.temp_c = row[2]
            r.humidity_pct = row[3]
            r.pressure_hpa = row[4]
            r.battery_v = row[5]
            r.observed_at = row[6]
            r.flags = row[7]
            latest = _latest_reading_from_row(r)
            traffic = _latest_traffic_from_row(row[8], row[9], row[10], row[11], row[12])
            activity_scores = await _compute_activity_scores(session, [hive_id])
            return _hive_out(hive, latest, traffic, activity_scores.get(hive_id))

    @router.patch("/hives/{hive_id}", response_model=HiveOut)
    async def patch_hive(hive_id: int, body: HiveUpdate, request: Request):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            stmt = select(Hive).where(Hive.id == hive_id)
            result = await session.execute(stmt)
            hive = result.scalar_one_or_none()
            if hive is None:
                raise HTTPException(status_code=404, detail="Hive not found")

            # Only update fields that were explicitly set in the request body
            for field_name in body.model_fields_set:
                setattr(hive, field_name, getattr(body, field_name))

            try:
                await session.commit()
            except IntegrityError:
                raise HTTPException(
                    status_code=409,
                    detail="Conflict: duplicate name or sender_mac",
                )
            await session.refresh(hive)
            return _hive_out(hive)

    @router.delete("/hives/{hive_id}", status_code=204)
    async def delete_hive(hive_id: int, request: Request):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            stmt = select(Hive).where(Hive.id == hive_id)
            result = await session.execute(stmt)
            hive = result.scalar_one_or_none()
            if hive is None:
                raise HTTPException(status_code=404, detail="Hive not found")

            await session.delete(hive)
            try:
                await session.commit()
            except IntegrityError:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot delete hive with existing readings",
                )
            return Response(status_code=204)

    return router
