"""Hives CRUD router."""

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive, SensorReading
from waggle.schemas import HiveCreate, HiveOut, HivesResponse, HiveUpdate, LatestReading
from waggle.utils.timestamps import utc_now


def _hive_out(hive: Hive, latest: LatestReading | None = None) -> HiveOut:
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
                raise HTTPException(status_code=409, detail="Hive with this id or name already exists")
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

            # Main query: hives left-joined with latest reading
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
                )
                .outerjoin(
                    latest_subq,
                    (Hive.id == latest_subq.c.hive_id) & (latest_subq.c.rn == 1),
                )
                .order_by(Hive.name.asc())
                .limit(limit)
                .offset(offset)
            )

            result = await session.execute(stmt)
            rows = result.all()

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
                items.append(_hive_out(hive, latest))

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
                )
                .outerjoin(
                    latest_subq,
                    (Hive.id == latest_subq.c.hive_id) & (latest_subq.c.rn == 1),
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
            return _hive_out(hive, latest)

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
                raise HTTPException(status_code=409, detail="Conflict: duplicate name or sender_mac")
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
