"""Varroa mite load tracking router."""

from datetime import UTC, datetime, timedelta

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Hive, Inspection, MlDetection
from waggle.schemas import VarroaDailyOut, VarroaSummaryOut


def create_router(verify_key) -> APIRouter:
    router = APIRouter(dependencies=[verify_key])

    async def _compute_daily_data(session, hive_id: int, days: int):
        """Compute daily varroa aggregates for a hive."""
        now = datetime.now(UTC)
        start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        # Get daily aggregates from ml_detections
        # Group by date portion of detected_at
        rows = (await session.execute(
            select(
                func.substr(MlDetection.detected_at, 1, 10).label("date"),
                func.sum(MlDetection.varroa_count).label("total_mites"),
                func.sum(MlDetection.bee_count).label("total_bees"),
                func.count(func.distinct(MlDetection.photo_id)).label("photo_count"),
            ).where(
                MlDetection.hive_id == hive_id,
                MlDetection.detected_at >= start,
            ).group_by(
                func.substr(MlDetection.detected_at, 1, 10)
            ).order_by(
                func.substr(MlDetection.detected_at, 1, 10).asc()
            )
        )).all()

        items = []
        for row in rows:
            total_mites = row.total_mites or 0
            total_bees = row.total_bees or 0
            ratio = (total_mites / total_bees * 100) if total_bees > 0 else None
            items.append(VarroaDailyOut(
                date=row.date,
                total_mites=total_mites,
                total_bees=total_bees,
                mites_per_100_bees=round(ratio, 2) if ratio is not None else None,
                photo_count=row.photo_count or 0,
            ))
        return items

    async def _compute_summary(
        session, hive_id: int, items: list[VarroaDailyOut], hive_name: str | None = None
    ):
        """Compute varroa summary from daily data."""
        # Current ratio
        current_ratio = items[-1].mites_per_100_bees if items else None

        # Trend: last 7 days with data
        ratios = [d.mites_per_100_bees for d in items[-7:] if d.mites_per_100_bees is not None]
        if len(ratios) < 3:
            trend_7d = "insufficient_data"
            trend_slope = None
        else:
            x = np.arange(len(ratios))
            coeffs = np.polyfit(x, ratios, 1)
            slope = float(coeffs[0])
            trend_slope = round(slope, 4)
            if abs(slope) < 0.1:
                trend_7d = "stable"
            elif slope > 0:
                trend_7d = "rising"
            else:
                trend_7d = "falling"

        # Days since treatment
        treatment = (await session.execute(
            select(Inspection.inspected_at).where(
                Inspection.hive_id == hive_id,
                Inspection.treatment_type.isnot(None),
            ).order_by(Inspection.inspected_at.desc()).limit(1)
        )).scalar_one_or_none()

        days_since = None
        if treatment:
            try:
                treatment_date = datetime.fromisoformat(treatment.replace("Z", "+00:00"))
                days_since = (datetime.now(UTC) - treatment_date).days
            except (ValueError, AttributeError):
                pass

        return VarroaSummaryOut(
            hive_id=hive_id,
            hive_name=hive_name,
            current_ratio=current_ratio,
            trend_7d=trend_7d,
            trend_slope=trend_slope,
            days_since_treatment=days_since,
        )

    @router.get("/hives/{hive_id}/varroa")
    async def get_varroa(
        request: Request,
        hive_id: int,
        days: int = Query(default=30, ge=1, le=365),
    ):
        async with AsyncSession(request.app.state.engine) as session:
            hive = await session.get(Hive, hive_id)
            if not hive:
                raise HTTPException(status_code=404, detail="Hive not found")

            items = await _compute_daily_data(session, hive_id, days)
            summary = await _compute_summary(session, hive_id, items, hive.name)
            return {
                "items": [item.model_dump() for item in items],
                "summary": summary.model_dump(),
            }

    @router.get("/varroa/overview")
    async def varroa_overview(request: Request):
        async with AsyncSession(request.app.state.engine) as session:
            hives = (await session.execute(select(Hive))).scalars().all()
            summaries = []
            for hive in hives:
                items = await _compute_daily_data(session, hive.id, 30)
                summary = await _compute_summary(session, hive.id, items, hive.name)
                summaries.append(summary.model_dump())
            return {"hives": summaries}

    return router
