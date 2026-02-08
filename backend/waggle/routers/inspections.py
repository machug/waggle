"""Inspections CRUD router."""

import uuid as uuid_mod

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive, Inspection
from waggle.schemas import InspectionIn, InspectionOut, InspectionsResponse, InspectionUpdate
from waggle.utils.timestamps import utc_now


def _inspection_out(insp: Inspection) -> InspectionOut:
    return InspectionOut(
        uuid=insp.uuid,
        hive_id=insp.hive_id,
        inspected_at=insp.inspected_at,
        updated_at=insp.updated_at,
        queen_seen=bool(insp.queen_seen),
        brood_pattern=insp.brood_pattern,
        treatment_type=insp.treatment_type,
        treatment_notes=insp.treatment_notes,
        notes=insp.notes,
        source=insp.source,
    )


def create_router(verify_key) -> APIRouter:
    router = APIRouter(dependencies=[verify_key])

    @router.post("/inspections", status_code=201)
    async def create_inspection(body: InspectionIn, request: Request):
        async with AsyncSession(request.app.state.engine) as session:
            # Validate hive exists
            hive = await session.get(Hive, body.hive_id)
            if not hive:
                raise HTTPException(status_code=404, detail="Hive not found")

            # Generate or use provided UUID
            inspection_uuid = body.uuid or str(uuid_mod.uuid4())

            # Idempotency check
            existing = await session.get(Inspection, inspection_uuid)
            if existing:
                return JSONResponse(
                    status_code=200,
                    content=_inspection_out(existing).model_dump(),
                )

            now = utc_now()
            insp = Inspection(
                uuid=inspection_uuid,
                hive_id=body.hive_id,
                inspected_at=body.inspected_at,
                created_at=now,
                updated_at=now,
                queen_seen=int(body.queen_seen),
                brood_pattern=body.brood_pattern,
                treatment_type=body.treatment_type,
                treatment_notes=body.treatment_notes,
                notes=body.notes,
                source="local",
            )
            session.add(insp)
            await session.commit()
            await session.refresh(insp)
            return JSONResponse(
                status_code=201,
                content=_inspection_out(insp).model_dump(),
            )

    @router.put("/inspections/{uuid}")
    async def update_inspection(uuid: str, body: InspectionUpdate, request: Request):
        async with AsyncSession(request.app.state.engine) as session:
            insp = await session.get(Inspection, uuid)
            if not insp:
                raise HTTPException(status_code=404, detail="Inspection not found")

            insp.hive_id = body.hive_id
            insp.inspected_at = body.inspected_at
            insp.queen_seen = int(body.queen_seen)
            insp.brood_pattern = body.brood_pattern
            insp.treatment_type = body.treatment_type
            insp.treatment_notes = body.treatment_notes
            insp.notes = body.notes
            insp.updated_at = utc_now()
            insp.row_synced = 0
            insp.source = "local"

            await session.commit()
            await session.refresh(insp)
            return _inspection_out(insp)

    @router.get("/hives/{hive_id}/inspections")
    async def list_inspections(
        request: Request,
        hive_id: int,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        order: str = Query(default="desc"),
    ):
        if order not in ("asc", "desc"):
            raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")

        async with AsyncSession(request.app.state.engine) as session:
            hive = await session.get(Hive, hive_id)
            if not hive:
                raise HTTPException(status_code=404, detail="Hive not found")

            base = select(Inspection).where(Inspection.hive_id == hive_id)
            count_q = (
                select(func.count()).select_from(Inspection).where(
                    Inspection.hive_id == hive_id
                )
            )

            if order == "desc":
                base = base.order_by(
                    Inspection.inspected_at.desc(), Inspection.uuid.desc()
                )
            else:
                base = base.order_by(
                    Inspection.inspected_at.asc(), Inspection.uuid.asc()
                )

            total = (await session.execute(count_q)).scalar()
            rows = (
                (await session.execute(base.offset(offset).limit(limit))).scalars().all()
            )

            return InspectionsResponse(
                items=[_inspection_out(r) for r in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    return router
