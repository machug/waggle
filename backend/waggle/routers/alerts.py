"""Alerts router — list with filtering and acknowledgment."""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Alert
from waggle.schemas import AlertAcknowledge, AlertOut, AlertsResponse
from waggle.utils.timestamps import utc_now


def _alert_out(alert: Alert) -> AlertOut:
    """Convert an Alert ORM instance to an AlertOut schema."""
    return AlertOut(
        id=alert.id,
        hive_id=alert.hive_id,
        reading_id=alert.reading_id,
        type=alert.type,
        severity=alert.severity,
        message=alert.message,
        acknowledged=bool(alert.acknowledged),
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        created_at=alert.created_at,
    )


def create_router(verify_key):
    router = APIRouter(tags=["alerts"], dependencies=[verify_key])

    @router.get("/alerts", response_model=AlertsResponse)
    async def list_alerts(
        request: Request,
        hive_id: int | None = Query(default=None),
        type: str | None = Query(default=None),
        severity: str | None = Query(default=None),
        acknowledged: bool | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            # Build base query with dynamic filters
            base = select(Alert)
            count_base = select(func.count()).select_from(Alert)

            if hive_id is not None:
                base = base.where(Alert.hive_id == hive_id)
                count_base = count_base.where(Alert.hive_id == hive_id)
            if type is not None:
                base = base.where(Alert.type == type)
                count_base = count_base.where(Alert.type == type)
            if severity is not None:
                base = base.where(Alert.severity == severity)
                count_base = count_base.where(Alert.severity == severity)
            if acknowledged is not None:
                ack_val = 1 if acknowledged else 0
                base = base.where(Alert.acknowledged == ack_val)
                count_base = count_base.where(Alert.acknowledged == ack_val)

            # Total count with filters
            total = (await session.execute(count_base)).scalar_one()

            # Fetch paginated results ordered by created_at DESC
            stmt = base.order_by(desc(Alert.created_at)).limit(limit).offset(offset)
            result = await session.execute(stmt)
            alerts = result.scalars().all()

            return AlertsResponse(
                items=[_alert_out(a) for a in alerts],
                total=total,
                limit=limit,
                offset=offset,
            )

    @router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
    async def acknowledge_alert(
        alert_id: int,
        request: Request,
        body: AlertAcknowledge | None = None,
    ):
        engine = request.app.state.engine
        async with AsyncSession(engine) as session:
            stmt = select(Alert).where(Alert.id == alert_id)
            result = await session.execute(stmt)
            alert = result.scalar_one_or_none()
            if alert is None:
                raise HTTPException(status_code=404, detail="Alert not found")

            # Idempotent: only update if not already acknowledged
            if not alert.acknowledged:
                alert.acknowledged = 1
                alert.acknowledged_at = utc_now()
                if body and body.acknowledged_by:
                    alert.acknowledged_by = body.acknowledged_by
                await session.commit()
                await session.refresh(alert)

            return _alert_out(alert)

    return router
