"""ML detection list router."""

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive, MlDetection
from waggle.schemas import DetectionOut, DetectionsResponse
from waggle.utils.timestamps import utc_now


def create_router(verify_key) -> APIRouter:
    router = APIRouter(dependencies=[verify_key])

    @router.get("/hives/{hive_id}/detections")
    async def list_detections(
        request: Request,
        hive_id: int,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = Query(default=None),
        class_: str | None = Query(default=None, alias="class"),
        min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        order: str = Query(default="desc"),
    ):
        if order not in ("asc", "desc"):
            raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")
        if class_ and class_ not in ("varroa", "pollen", "wasp", "bee", "normal"):
            raise HTTPException(status_code=400, detail="Invalid class value")

        async with AsyncSession(request.app.state.engine) as session:
            hive = await session.get(Hive, hive_id)
            if not hive:
                raise HTTPException(status_code=404, detail="Hive not found")

            now = utc_now()
            if not from_:
                from_ = (datetime.now(UTC) - timedelta(hours=24)).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                )[:-3] + "Z"
            if not to:
                to = now

            filters = [
                MlDetection.hive_id == hive_id,
                MlDetection.detected_at >= from_,
                MlDetection.detected_at <= to,
                MlDetection.top_confidence >= min_confidence,
            ]
            if class_:
                filters.append(MlDetection.top_class == class_)

            query = select(MlDetection).where(*filters)
            count_query = select(func.count()).select_from(MlDetection).where(*filters)

            if order == "desc":
                query = query.order_by(
                    MlDetection.detected_at.desc(), MlDetection.id.desc()
                )
            else:
                query = query.order_by(
                    MlDetection.detected_at.asc(), MlDetection.id.asc()
                )

            total = (await session.execute(count_query)).scalar()
            rows = (
                (await session.execute(query.offset(offset).limit(limit))).scalars().all()
            )

            items = []
            for d in rows:
                detections_json = json.loads(d.detections_json) if d.detections_json else []
                items.append(
                    DetectionOut(
                        id=d.id,
                        photo_id=d.photo_id,
                        hive_id=d.hive_id,
                        detected_at=d.detected_at,
                        top_class=d.top_class,
                        top_confidence=d.top_confidence,
                        detections_json=detections_json,
                        varroa_count=d.varroa_count,
                        pollen_count=d.pollen_count,
                        wasp_count=d.wasp_count,
                        bee_count=d.bee_count,
                        inference_ms=d.inference_ms,
                        model_version=d.model_version,
                        model_hash=d.model_hash,
                    )
                )

            return DetectionsResponse(
                items=items, total=total, limit=limit, offset=offset
            )

    return router
