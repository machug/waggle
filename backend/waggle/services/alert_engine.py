"""Alert engine: checks rules after each sensor reading ingestion.

Phase 1 rules:
- POSSIBLE_SWARM (weight-only fallback): Weight dropped >2kg in last hour (high, 12h cooldown)
- HIGH_TEMP: temp_c > 40C (medium, 30min cooldown)
- LOW_TEMP: temp_c < 5C (low, 30min cooldown)
- LOW_BATTERY: battery_v < 3.3V (medium, 60min cooldown)
- NO_DATA: No reading for >15min (medium, 60min cooldown)

Phase 2 correlation rules (require bee_counts data):
- POSSIBLE_SWARM (correlation): Weight drop >1.5kg AND net_out >500 in 1h (critical, 12h cooldown)
- ABSCONDING: Weight drop >2.0kg AND net_out >400 over 2h (critical, 24h cooldown)
- ROBBING: total_traffic >1000/hr AND net_out <-200 AND weight >0.5kg (high, 4h)
- LOW_ACTIVITY: today's total_traffic <20% of 7-day avg (medium, 24h cooldown)

Phase 3 ML-based rules (triggered after ML inference):
- VARROA_DETECTED: varroa_max_confidence >= 0.7 (low, 24h cooldown)
- VARROA_HIGH_LOAD: mites_per_100_bees > 3.0 today (critical, 48h cooldown)
- VARROA_RISING: 7-day slope > 0.3/day AND ratio > 1.0 (high, 72h cooldown)
- WASP_ATTACK: 3+ wasp detections in 10 minutes (high, 2h cooldown)
"""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from waggle.models import Alert, Hive, MlDetection, SensorReading
from waggle.utils.timestamps import utc_now


class AlertEngine:
    """Evaluates alert rules against sensor readings and hive state."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def check_reading(self, hive_id: int, reading: dict) -> list[dict]:
        """Check all rules for a new reading. Returns list of fired alerts.

        reading dict has keys: weight_kg, temp_c, humidity_pct, pressure_hpa,
        battery_v, observed_at, flags (all post-conversion, may be None).
        Phase 2 also passes: bees_in, bees_out, period_ms, lane_mask, stuck_mask
        """
        alerts = []
        observed_at = reading["observed_at"]
        async with AsyncSession(self.engine) as session:
            # Phase 1 simple threshold rules
            if await self._check_high_temp(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    "HIGH_TEMP",
                    "medium",
                    f"Temperature {reading['temp_c']:.1f}C exceeds 40C threshold",
                    observed_at=observed_at,
                )
                alerts.append(alert)
            if await self._check_low_temp(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    "LOW_TEMP",
                    "low",
                    f"Temperature {reading['temp_c']:.1f}C below 5C threshold",
                    observed_at=observed_at,
                )
                alerts.append(alert)
            if await self._check_low_battery(session, hive_id, reading):
                alert = await self._fire(
                    session,
                    hive_id,
                    "LOW_BATTERY",
                    "medium",
                    f"Battery {reading['battery_v']:.2f}V below 3.3V threshold",
                    observed_at=observed_at,
                )
                alerts.append(alert)

            # POSSIBLE_SWARM: try correlation rule first, fall back to weight-only
            swarm_result = await self._check_swarm_correlation(session, hive_id, reading)
            if swarm_result is not None:
                # Correlation rule evaluated (traffic data exists)
                if swarm_result:
                    wt_drop, net_out, count = swarm_result
                    alert = await self._fire(
                        session,
                        hive_id,
                        "POSSIBLE_SWARM",
                        "critical",
                        f"Weight dropped {wt_drop:.1f}kg with net_out {net_out}"
                        f" in 1h ({count} readings)",
                        observed_at=observed_at,
                    )
                    alerts.append(alert)
            else:
                # No traffic data — fall back to Phase 1 weight-only rule
                if await self._check_swarm(session, hive_id, reading):
                    alert = await self._fire(
                        session,
                        hive_id,
                        "POSSIBLE_SWARM",
                        "high",
                        f"Weight dropped >2kg in last hour"
                        f" (current: {reading['weight_kg']:.1f}kg)",
                        observed_at=observed_at,
                    )
                    alerts.append(alert)

            # Phase 2 correlation rules
            absconding = await self._check_absconding(session, hive_id, reading)
            if absconding:
                wt_drop, net_out, count = absconding
                alert = await self._fire(
                    session,
                    hive_id,
                    "ABSCONDING",
                    "critical",
                    f"Weight dropped {wt_drop:.1f}kg with net_out {net_out}"
                    f" in 2h ({count} readings)",
                    observed_at=observed_at,
                )
                alerts.append(alert)

            robbing = await self._check_robbing(session, hive_id, reading)
            if robbing:
                wt_drop, traffic, net_out, count = robbing
                alert = await self._fire(
                    session,
                    hive_id,
                    "ROBBING",
                    "high",
                    f"High traffic {traffic} with net_out {net_out}"
                    f" and weight drop {wt_drop:.1f}kg in 1h ({count} readings)",
                    observed_at=observed_at,
                )
                alerts.append(alert)

            low_act = await self._check_low_activity(session, hive_id, reading)
            if low_act:
                today_total, avg_daily, num_days = low_act
                alert = await self._fire(
                    session,
                    hive_id,
                    "LOW_ACTIVITY",
                    "medium",
                    f"Today's traffic {today_total} is <20% of"
                    f" 7-day avg {avg_daily:.0f} ({num_days} days)",
                    observed_at=observed_at,
                )
                alerts.append(alert)

            await session.commit()
        return alerts

    async def check_no_data(self) -> list[dict]:
        """Check all hives for stale data. Called by scheduler every 60s."""
        alerts = []
        cutoff = (datetime.now(UTC) - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ] + "Z"
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
                        "NO_DATA",
                        "medium",
                        f"No data received from hive '{hive.name}' for >15 minutes",
                        observed_at=utc_now(),
                    )
                    alerts.append(alert)
            await session.commit()
        return alerts

    # ---- Rule checks ----

    async def _check_high_temp(self, session: AsyncSession, hive_id: int, reading: dict) -> bool:
        if reading.get("temp_c") is None:
            return False
        if reading["temp_c"] <= 40.0:
            return False
        return not await self._cooldown_active(session, hive_id, "HIGH_TEMP", 30)

    async def _check_low_temp(self, session: AsyncSession, hive_id: int, reading: dict) -> bool:
        if reading.get("temp_c") is None:
            return False
        if reading["temp_c"] >= 5.0:
            return False
        return not await self._cooldown_active(session, hive_id, "LOW_TEMP", 30)

    async def _check_low_battery(self, session: AsyncSession, hive_id: int, reading: dict) -> bool:
        if reading.get("battery_v") is None:
            return False
        if reading["battery_v"] >= 3.3:
            return False
        return not await self._cooldown_active(session, hive_id, "LOW_BATTERY", 60)

    async def _check_swarm(self, session: AsyncSession, hive_id: int, reading: dict) -> bool:
        if reading.get("weight_kg") is None:
            return False

        current_weight = reading["weight_kg"]
        observed_at = reading["observed_at"]

        # Anchor to reading's observed_at, NOT system clock
        reading_time = datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        cutoff = (reading_time - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

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

        return not await self._cooldown_active(session, hive_id, "POSSIBLE_SWARM", 720)

    # ---- Phase 2 correlation rule checks ----

    @staticmethod
    def _iso_cutoff(reading_time: datetime, hours: int) -> str:
        """Compute ISO 8601 cutoff string anchored to reading time."""
        return (reading_time - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    @staticmethod
    def _parse_observed_at(observed_at: str) -> datetime:
        """Parse an ISO 8601 observed_at string to a UTC datetime."""
        return datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)

    async def _check_swarm_correlation(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> tuple[float, int, int] | None | bool:
        """Check Phase 2 correlation swarm rule.

        Returns:
            None  — no traffic data exists, caller should fall back to Phase 1
            False — traffic data exists but thresholds not met
            (weight_drop, net_out, count) — thresholds met, alert should fire
        """
        if reading.get("weight_kg") is None:
            return None

        observed_at = reading["observed_at"]
        reading_time = self._parse_observed_at(observed_at)
        from_1h = self._iso_cutoff(reading_time, 1)

        # First check if ANY bee_counts exist for this hive in the 1h window
        count_result = await session.execute(
            text(
                "SELECT COUNT(*) FROM bee_counts"
                " WHERE hive_id = :hive_id"
                " AND observed_at >= :from_1h"
                " AND observed_at <= :now_dt"
            ),
            {"hive_id": hive_id, "from_1h": from_1h, "now_dt": observed_at},
        )
        traffic_count = count_result.scalar()
        if not traffic_count or traffic_count == 0:
            return None  # No traffic data — fall back to Phase 1

        # Traffic data exists — evaluate correlation rule
        if await self._cooldown_active(session, hive_id, "POSSIBLE_SWARM", 720):
            return False

        result = await session.execute(
            text(
                "WITH hour_data AS ("
                "  SELECT sr.weight_kg, bc.net_out, bc.total_traffic, sr.observed_at"
                "  FROM sensor_readings sr"
                "  JOIN bee_counts bc ON bc.reading_id = sr.id"
                "  WHERE sr.hive_id = :hive_id"
                "    AND sr.observed_at >= :from_1h"
                "    AND sr.observed_at <= :now_dt"
                "    AND (sr.flags & 0x02) = 0"
                "    AND (sr.flags & 0x40) = 0"
                "    AND bc.stuck_mask = 0"
                "),"
                "weight_range AS ("
                "  SELECT MAX(weight_kg) AS max_wt,"
                "    (SELECT weight_kg FROM hour_data"
                "     ORDER BY observed_at DESC LIMIT 1) AS cur_wt"
                "  FROM hour_data"
                ")"
                " SELECT max_wt - cur_wt AS weight_drop_kg,"
                "   SUM(net_out) AS total_net_out,"
                "   COUNT(*) AS reading_count"
                " FROM hour_data, weight_range"
                " HAVING reading_count >= 30"
                "   AND weight_drop_kg > 1.5"
                "   AND total_net_out > 500"
            ),
            {"hive_id": hive_id, "from_1h": from_1h, "now_dt": observed_at},
        )
        row = result.fetchone()
        if row is None:
            return False

        return (row[0], row[1], row[2])

    async def _check_absconding(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> tuple[float, int, int] | bool:
        """Check ABSCONDING rule: weight drop >2.0kg AND net_out >400 over 2h.

        Returns False or (weight_drop, net_out, count).
        """
        if reading.get("weight_kg") is None:
            return False

        observed_at = reading["observed_at"]
        reading_time = self._parse_observed_at(observed_at)
        from_2h = self._iso_cutoff(reading_time, 2)

        if await self._cooldown_active(session, hive_id, "ABSCONDING", 1440):
            return False

        result = await session.execute(
            text(
                "WITH two_hour_data AS ("
                "  SELECT sr.weight_kg, bc.net_out, sr.observed_at"
                "  FROM sensor_readings sr"
                "  JOIN bee_counts bc ON bc.reading_id = sr.id"
                "  WHERE sr.hive_id = :hive_id"
                "    AND sr.observed_at >= :from_2h"
                "    AND sr.observed_at <= :now_dt"
                "    AND (sr.flags & 0x02) = 0"
                "    AND (sr.flags & 0x40) = 0"
                "    AND bc.stuck_mask = 0"
                "),"
                "weight_range AS ("
                "  SELECT MAX(weight_kg) AS max_wt,"
                "    (SELECT weight_kg FROM two_hour_data"
                "     ORDER BY observed_at DESC LIMIT 1) AS cur_wt"
                "  FROM two_hour_data"
                ")"
                " SELECT max_wt - cur_wt AS weight_drop_kg,"
                "   SUM(net_out) AS total_net_out,"
                "   COUNT(*) AS reading_count"
                " FROM two_hour_data, weight_range"
                " HAVING reading_count >= 60"
                "   AND weight_drop_kg > 2.0"
                "   AND total_net_out > 400"
            ),
            {"hive_id": hive_id, "from_2h": from_2h, "now_dt": observed_at},
        )
        row = result.fetchone()
        if row is None:
            return False

        return (row[0], row[1], row[2])

    async def _check_robbing(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> tuple[float, int, int, int] | bool:
        """Check ROBBING rule: total_traffic >1000/hr AND net_out <-200 AND weight drop >0.5kg.

        Returns False or (weight_drop, total_traffic, net_out, count).
        """
        if reading.get("weight_kg") is None:
            return False

        observed_at = reading["observed_at"]
        reading_time = self._parse_observed_at(observed_at)
        from_1h = self._iso_cutoff(reading_time, 1)

        if await self._cooldown_active(session, hive_id, "ROBBING", 240):
            return False

        result = await session.execute(
            text(
                "WITH hour_data AS ("
                "  SELECT sr.weight_kg, bc.total_traffic, bc.net_out, sr.observed_at"
                "  FROM sensor_readings sr"
                "  JOIN bee_counts bc ON bc.reading_id = sr.id"
                "  WHERE sr.hive_id = :hive_id"
                "    AND sr.observed_at >= :from_1h"
                "    AND sr.observed_at <= :now_dt"
                "    AND (sr.flags & 0x02) = 0"
                "    AND (sr.flags & 0x40) = 0"
                "    AND bc.stuck_mask = 0"
                "),"
                "weight_range AS ("
                "  SELECT MAX(weight_kg) AS max_wt,"
                "    (SELECT weight_kg FROM hour_data"
                "     ORDER BY observed_at DESC LIMIT 1) AS cur_wt"
                "  FROM hour_data"
                ")"
                " SELECT max_wt - cur_wt AS weight_drop_kg,"
                "   SUM(total_traffic) AS hour_total_traffic,"
                "   SUM(net_out) AS hour_net_out,"
                "   COUNT(*) AS reading_count"
                " FROM hour_data, weight_range"
                " HAVING reading_count >= 30"
                "   AND weight_drop_kg > 0.5"
                "   AND hour_total_traffic > 1000"
                "   AND hour_net_out < -200"
            ),
            {"hive_id": hive_id, "from_1h": from_1h, "now_dt": observed_at},
        )
        row = result.fetchone()
        if row is None:
            return False

        return (row[0], row[1], row[2], row[3])

    async def _check_low_activity(
        self, session: AsyncSession, hive_id: int, reading: dict
    ) -> tuple[int, float, int] | bool:
        """Check LOW_ACTIVITY rule: today's traffic <20% of 7-day rolling avg.

        Returns False or (today_total, avg_daily, num_days).
        """
        observed_at = reading["observed_at"]
        reading_time = self._parse_observed_at(observed_at)

        # Compute day boundaries anchored to reading's observed_at
        today_start = reading_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        yesterday_end = today_start  # exclusive upper bound for historical data
        week_start = today_start - timedelta(days=7)

        def _fmt(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        if await self._cooldown_active(session, hive_id, "LOW_ACTIVITY", 1440):
            return False

        result = await session.execute(
            text(
                "WITH today AS ("
                "  SELECT COALESCE(SUM(bc.total_traffic), 0) AS today_total"
                "  FROM bee_counts bc"
                "  JOIN sensor_readings sr ON sr.id = bc.reading_id"
                "  WHERE bc.hive_id = :hive_id"
                "    AND bc.observed_at >= :today_start"
                "    AND bc.observed_at < :today_end"
                "    AND (sr.flags & 0x02) = 0"
                "    AND (sr.flags & 0x40) = 0"
                "    AND bc.stuck_mask = 0"
                "),"
                "avg_7d AS ("
                "  SELECT COALESCE(AVG(day_total), 0) AS avg_daily,"
                "    COUNT(*) AS num_days"
                "  FROM ("
                "    SELECT substr(bc.observed_at, 1, 10) AS day,"
                "      SUM(bc.total_traffic) AS day_total"
                "    FROM bee_counts bc"
                "    JOIN sensor_readings sr ON sr.id = bc.reading_id"
                "    WHERE bc.hive_id = :hive_id"
                "      AND bc.observed_at >= :week_start"
                "      AND bc.observed_at < :yesterday_end"
                "      AND (sr.flags & 0x02) = 0"
                "      AND (sr.flags & 0x40) = 0"
                "      AND bc.stuck_mask = 0"
                "    GROUP BY day"
                "    HAVING COUNT(*) >= 10"
                "  )"
                ")"
                " SELECT today_total, avg_daily, num_days"
                " FROM today, avg_7d"
                " WHERE num_days >= 3"
                "   AND avg_daily > 0"
                "   AND today_total < 0.2 * avg_daily"
            ),
            {
                "hive_id": hive_id,
                "today_start": _fmt(today_start),
                "today_end": _fmt(today_end),
                "week_start": _fmt(week_start),
                "yesterday_end": _fmt(yesterday_end),
            },
        )
        row = result.fetchone()
        if row is None:
            return False

        return (row[0], row[1], row[2])

    # ---- Shared helpers ----

    async def _cooldown_active(
        self,
        session: AsyncSession,
        hive_id: int,
        alert_type: str,
        cooldown_min: int,
    ) -> bool:
        """Check if an alert of this type was recently fired for this hive."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=cooldown_min)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
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
        alert_type: str,
        severity: str,
        message: str,
        observed_at: str | None = None,
        details_json: str | None = None,
    ) -> dict:
        """Insert an alert into the database and return its dict representation."""
        now = utc_now()
        alert = Alert(
            hive_id=hive_id,
            type=alert_type,
            severity=severity,
            message=message,
            observed_at=observed_at or now,
            created_at=now,
            updated_at=now,
        )
        if details_json:
            alert.details_json = details_json
        session.add(alert)
        await session.flush()  # Get the auto-generated id
        return {
            "id": alert.id,
            "hive_id": hive_id,
            "type": alert_type,
            "severity": severity,
            "message": message,
            "observed_at": alert.observed_at,
            "created_at": now,
        }

    # ---- Phase 3 ML alert rules ----

    async def check_ml_alerts(self, hive_id: int) -> list[dict]:
        """Evaluate all ML-based alert rules for a hive. Called after ML inference."""
        alerts = []
        async with AsyncSession(self.engine) as session:
            alert = await self._check_varroa_detected(session, hive_id)
            if alert:
                alerts.append(alert)
            alert = await self._check_varroa_high_load(session, hive_id)
            if alert:
                alerts.append(alert)
            alert = await self._check_varroa_rising(session, hive_id)
            if alert:
                alerts.append(alert)
            alert = await self._check_wasp_attack(session, hive_id)
            if alert:
                alerts.append(alert)
            await session.commit()
        return alerts

    async def _check_varroa_detected(self, session: AsyncSession, hive_id: int) -> dict | None:
        """VARROA_DETECTED: latest detection with varroa_max_confidence >= 0.7."""
        if await self._cooldown_active(session, hive_id, "VARROA_DETECTED", 1440):
            return None

        result = await session.execute(
            select(MlDetection)
            .where(
                MlDetection.hive_id == hive_id,
                MlDetection.varroa_max_confidence >= 0.7,
            )
            .order_by(MlDetection.detected_at.desc())
            .limit(1)
        )
        detection = result.scalar_one_or_none()
        if detection is None:
            return None

        details = json.dumps(
            {
                "photo_id": detection.photo_id,
                "confidence": detection.varroa_max_confidence,
                "model_hash": detection.model_hash,
            }
        )
        return await self._fire(
            session,
            hive_id,
            "VARROA_DETECTED",
            "low",
            f"Varroa mite detected with {detection.varroa_max_confidence:.0%} confidence",
            observed_at=detection.detected_at,
            details_json=details,
        )

    async def _check_varroa_high_load(self, session: AsyncSession, hive_id: int) -> dict | None:
        """VARROA_HIGH_LOAD: today's mites_per_100_bees > 3.0."""
        if await self._cooldown_active(session, hive_id, "VARROA_HIGH_LOAD", 2880):
            return None

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_cutoff = today_start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        result = await session.execute(
            select(
                func.sum(MlDetection.varroa_count).label("total_varroa"),
                func.sum(MlDetection.bee_count).label("total_bees"),
                func.count().label("sample_count"),
            ).where(
                MlDetection.hive_id == hive_id,
                MlDetection.detected_at >= today_cutoff,
            )
        )
        row = result.one()
        total_varroa = row.total_varroa or 0
        total_bees = row.total_bees or 0
        sample_count = row.sample_count or 0

        if total_bees == 0 or sample_count == 0:
            return None

        mites_per_100 = total_varroa * 100.0 / total_bees
        if mites_per_100 <= 3.0:
            return None

        details = json.dumps(
            {
                "mites_per_100_bees": round(mites_per_100, 2),
                "sample_count": sample_count,
            }
        )
        return await self._fire(
            session,
            hive_id,
            "VARROA_HIGH_LOAD",
            "critical",
            f"Varroa load {mites_per_100:.1f} mites/100 bees exceeds threshold",
            observed_at=utc_now(),
            details_json=details,
        )

    async def _check_varroa_rising(self, session: AsyncSession, hive_id: int) -> dict | None:
        """VARROA_RISING: 7-day slope > 0.3/day AND latest ratio > 1.0."""
        if await self._cooldown_active(session, hive_id, "VARROA_RISING", 4320):
            return None

        now = datetime.now(UTC)
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        # Get daily averages of mites_per_100_bees for last 7 days
        result = await session.execute(
            text(
                "SELECT substr(detected_at, 1, 10) AS day,"
                " SUM(varroa_count) * 100.0 / NULLIF(SUM(bee_count), 0) AS ratio"
                " FROM ml_detections"
                " WHERE hive_id = :hive_id"
                "   AND detected_at >= :week_start"
                "   AND bee_count > 0"
                " GROUP BY day"
                " ORDER BY day"
            ),
            {"hive_id": hive_id, "week_start": week_start},
        )
        rows = result.fetchall()
        if len(rows) < 3:
            return None

        # Compute linear slope: slope of (day_index, ratio) pairs
        n = len(rows)
        x_vals = list(range(n))
        y_vals = [float(r[1]) for r in rows]

        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator == 0:
            return None

        slope = numerator / denominator
        latest_ratio = y_vals[-1]

        if slope <= 0.3 or latest_ratio <= 1.0:
            return None

        details = json.dumps(
            {
                "slope": round(slope, 4),
                "latest_ratio": round(latest_ratio, 2),
                "days": n,
            }
        )
        return await self._fire(
            session,
            hive_id,
            "VARROA_RISING",
            "high",
            f"Varroa trend rising at {slope:.2f}/day, current {latest_ratio:.1f} mites/100 bees",
            observed_at=utc_now(),
            details_json=details,
        )

    async def _check_wasp_attack(self, session: AsyncSession, hive_id: int) -> dict | None:
        """WASP_ATTACK: 3+ wasp detections in last 10 minutes."""
        if await self._cooldown_active(session, hive_id, "WASP_ATTACK", 120):
            return None

        cutoff_10m = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ] + "Z"

        result = await session.execute(
            select(
                func.sum(MlDetection.wasp_count).label("total_wasps"),
                func.group_concat(MlDetection.photo_id).label("photo_ids"),
            ).where(
                MlDetection.hive_id == hive_id,
                MlDetection.detected_at >= cutoff_10m,
                MlDetection.wasp_count >= 1,
            )
        )
        row = result.one()
        total_wasps = row.total_wasps or 0

        if total_wasps < 3:
            return None

        photo_ids_str = row.photo_ids or ""
        photo_ids = [int(pid) for pid in photo_ids_str.split(",") if pid]

        details = json.dumps(
            {
                "wasp_count": total_wasps,
                "window_minutes": 10,
                "photo_ids": photo_ids,
            }
        )
        return await self._fire(
            session,
            hive_id,
            "WASP_ATTACK",
            "high",
            f"Wasp attack detected: {total_wasps} wasps in last 10 minutes",
            observed_at=utc_now(),
            details_json=details,
        )
