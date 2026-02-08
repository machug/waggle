"""Alert engine: checks 5 rules after each sensor reading ingestion.

Rules:
- POSSIBLE_SWARM: Weight dropped >2kg in last hour (high, 12h cooldown)
- HIGH_TEMP: temp_c > 40C (medium, 30min cooldown)
- LOW_TEMP: temp_c < 5C (low, 30min cooldown)
- LOW_BATTERY: battery_v < 3.3V (medium, 60min cooldown)
- NO_DATA: No reading for >15min (medium, 60min cooldown)
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from waggle.models import Alert, Hive, SensorReading
from waggle.utils.timestamps import utc_now


class AlertEngine:
    """Evaluates alert rules against sensor readings and hive state."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def check_reading(
        self, hive_id: int, reading_id: int, reading: dict
    ) -> list[dict]:
        """Check all rules for a new reading. Returns list of fired alerts.

        reading dict has keys: weight_kg, temp_c, humidity_pct, pressure_hpa,
        battery_v, observed_at, flags (all post-conversion, may be None)
        """
        alerts = []
        async with AsyncSession(self.engine) as session:
            if await self._check_high_temp(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    reading_id,
                    "HIGH_TEMP",
                    "medium",
                    f"Temperature {reading['temp_c']:.1f}C exceeds 40C threshold",
                )
                alerts.append(alert)
            if await self._check_low_temp(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    reading_id,
                    "LOW_TEMP",
                    "low",
                    f"Temperature {reading['temp_c']:.1f}C below 5C threshold",
                )
                alerts.append(alert)
            if await self._check_low_battery(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    reading_id,
                    "LOW_BATTERY",
                    "medium",
                    f"Battery {reading['battery_v']:.2f}V below 3.3V threshold",
                )
                alerts.append(alert)
            if await self._check_swarm(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    reading_id,
                    "POSSIBLE_SWARM",
                    "high",
                    f"Weight dropped >2kg in last hour (current: {reading['weight_kg']:.1f}kg)",
                )
                alerts.append(alert)
            await session.commit()
        return alerts

    async def check_no_data(self) -> list[dict]:
        """Check all hives for stale data. Called by scheduler every 60s."""
        alerts = []
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Hive).where(
                    Hive.last_seen_at.isnot(None),
                    Hive.last_seen_at < cutoff,
                )
            )
            stale_hives = result.scalars().all()
            for hive in stale_hives:
                if not await self._cooldown_active(session, hive.id, "NO_DATA", 60):
                    alert = await self._fire(
                        session,
                        hive.id,
                        None,
                        "NO_DATA",
                        "medium",
                        f"No data received from hive '{hive.name}' for >15 minutes",
                    )
                    alerts.append(alert)
            await session.commit()
        return alerts

    # ---- Rule checks ----

    async def _check_high_temp(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> bool:
        if reading.get("temp_c") is None:
            return False
        if reading["temp_c"] <= 40.0:
            return False
        return not await self._cooldown_active(session, hive_id, "HIGH_TEMP", 30)

    async def _check_low_temp(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> bool:
        if reading.get("temp_c") is None:
            return False
        if reading["temp_c"] >= 5.0:
            return False
        return not await self._cooldown_active(session, hive_id, "LOW_TEMP", 30)

    async def _check_low_battery(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> bool:
        if reading.get("battery_v") is None:
            return False
        if reading["battery_v"] >= 3.3:
            return False
        return not await self._cooldown_active(session, hive_id, "LOW_BATTERY", 60)

    async def _check_swarm(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> bool:
        if reading.get("weight_kg") is None:
            return False

        current_weight = reading["weight_kg"]
        observed_at = reading["observed_at"]

        # Anchor to reading's observed_at, NOT system clock
        reading_time = datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
        cutoff = (reading_time - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"

        # Get readings from the hour preceding this reading
        result = await session.execute(
            select(SensorReading.weight_kg)
            .where(
                SensorReading.hive_id == hive_id,
                SensorReading.observed_at >= cutoff,
                SensorReading.observed_at <= observed_at,
                SensorReading.weight_kg.isnot(None),
            )
            .order_by(SensorReading.observed_at.asc())
        )
        rows = result.scalars().all()

        if len(rows) < 5:
            return False

        max_weight = max(rows)
        if (max_weight - current_weight) <= 2.0:
            return False

        return not await self._cooldown_active(
            session, hive_id, "POSSIBLE_SWARM", 720
        )

    # ---- Shared helpers ----

    async def _cooldown_active(
        self,
        session: AsyncSession,
        hive_id: int,
        alert_type: str,
        cooldown_min: int,
    ) -> bool:
        """Check if an alert of this type was recently fired for this hive."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=cooldown_min)
        ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        result = await session.execute(
            select(Alert.id)
            .where(
                Alert.hive_id == hive_id,
                Alert.type == alert_type,
                Alert.created_at > cutoff,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _fire(
        self,
        session: AsyncSession,
        hive_id: int,
        reading_id: int | None,
        alert_type: str,
        severity: str,
        message: str,
    ) -> dict:
        """Insert an alert into the database and return its dict representation."""
        now = utc_now()
        alert = Alert(
            hive_id=hive_id,
            reading_id=reading_id,
            type=alert_type,
            severity=severity,
            message=message,
            created_at=now,
        )
        session.add(alert)
        await session.flush()  # Get the auto-generated id
        return {
            "id": alert.id,
            "hive_id": hive_id,
            "reading_id": reading_id,
            "type": alert_type,
            "severity": severity,
            "message": message,
            "created_at": now,
        }
