"""Worker ingestion service — processes MQTT sensor messages."""

import logging
import re
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from waggle.config import Settings
from waggle.models import Hive, SensorReading
from waggle.services.alert_engine import AlertEngine
from waggle.utils.timestamps import is_system_time_valid, utc_now, validate_observed_at

logger = logging.getLogger(__name__)

# Flag bit positions
FLAG_FIRST_BOOT = 1 << 1  # bit 1
FLAG_HX711_ERROR = 1 << 3  # bit 3
FLAG_BME280_ERROR = 1 << 4  # bit 4
FLAG_BATTERY_ERROR = 1 << 5  # bit 5

# Dedup constants
DEDUP_TTL_SECONDS = 30 * 60  # 30 minutes
DEDUP_MAX_PER_HIVE = 256

# Range limits: (field_name, min, max)
RANGE_LIMITS = {
    "weight_kg": (0, 200),
    "temp_c": (-20, 60),
    "humidity_pct": (0, 100),
    "pressure_hpa": (300, 1100),
    "battery_v": (2.5, 4.5),
}

# Topic pattern: waggle/{hive_id}/sensors
TOPIC_RE = re.compile(r"^waggle/(\d+)/sensors$")


class IngestionService:
    """Processes MQTT sensor messages through the validation/dedup/storage pipeline."""

    def __init__(
        self, engine: AsyncEngine, settings: Settings, alert_engine: AlertEngine
    ):
        self.engine = engine
        self.settings = settings
        self.alert_engine = alert_engine
        self._dedup_cache: dict[int, dict[int, float]] = {}  # hive_id -> {sequence: timestamp}

    async def warm_dedup_cache(self) -> None:
        """Populate dedup cache from recent DB readings on startup."""
        cutoff = (
            datetime.now(UTC) - timedelta(seconds=DEDUP_TTL_SECONDS)
        ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(SensorReading.hive_id, SensorReading.sequence)
                .where(SensorReading.ingested_at >= cutoff)
            )
            for row in result:
                hive_id, sequence = row.hive_id, row.sequence
                if hive_id not in self._dedup_cache:
                    self._dedup_cache[hive_id] = {}
                self._dedup_cache[hive_id][sequence] = time.monotonic()

    async def process_message(self, topic: str, payload: dict) -> bool:
        """Process a single MQTT sensor message.

        Returns True if stored, False if dropped.
        """
        # 1. System time check
        if not is_system_time_valid(self.settings.MIN_VALID_YEAR):
            logger.warning("System time invalid, dropping message")
            return False

        # 2. Schema version
        if payload.get("schema_version") != 1:
            logger.warning("Bad schema_version: %s", payload.get("schema_version"))
            return False

        # 3. Topic hive_id match
        topic_match = TOPIC_RE.match(topic)
        if not topic_match:
            logger.warning("Invalid topic format: %s", topic)
            return False

        topic_hive_id = int(topic_match.group(1))
        payload_hive_id = payload.get("hive_id")
        if topic_hive_id != payload_hive_id:
            logger.warning(
                "Topic/payload hive_id mismatch: topic=%d payload=%s",
                topic_hive_id,
                payload_hive_id,
            )
            return False

        hive_id = topic_hive_id

        # 4. Hive exists + get sender_mac
        async with AsyncSession(self.engine) as session:
            hive = (
                await session.execute(select(Hive).where(Hive.id == hive_id))
            ).scalar_one_or_none()

        if hive is None:
            logger.warning("Unknown hive_id: %d", hive_id)
            return False

        # 5. msg_type
        if payload.get("msg_type") != 1:
            logger.warning("Bad msg_type: %s", payload.get("msg_type"))
            return False

        # 6. MAC check
        if hive.sender_mac is not None:
            payload_mac = payload.get("sender_mac", "")
            if payload_mac.upper() != hive.sender_mac.upper():
                logger.warning(
                    "MAC mismatch: expected=%s got=%s",
                    hive.sender_mac,
                    payload_mac,
                )
                return False

        # 7. Timestamp validation
        observed_at = payload.get("observed_at")
        if not validate_observed_at(
            observed_at, max_past_skew_hours=self.settings.MAX_PAST_SKEW_HOURS
        ):
            logger.warning("Invalid observed_at: %s", observed_at)
            return False

        # 8. Error flag handling
        flags = payload.get("flags", 0)

        hx711_error = bool(flags & FLAG_HX711_ERROR)
        bme280_error = bool(flags & FLAG_BME280_ERROR)
        battery_error = bool(flags & FLAG_BATTERY_ERROR)

        # 9. Unit conversion (None if sensor error)
        weight_kg = None if hx711_error else payload["weight_g"] / 1000.0
        temp_c = None if bme280_error else payload["temp_c_x100"] / 100.0
        humidity_pct = None if bme280_error else payload["humidity_x100"] / 100.0
        pressure_hpa = None if bme280_error else payload["pressure_hpa_x10"] / 10.0
        battery_v = None if battery_error else payload["battery_mv"] / 1000.0

        # 10. Range validation (for non-None fields)
        converted = {
            "weight_kg": weight_kg,
            "temp_c": temp_c,
            "humidity_pct": humidity_pct,
            "pressure_hpa": pressure_hpa,
            "battery_v": battery_v,
            "observed_at": observed_at,
            "flags": flags,
        }
        for field, value in converted.items():
            if field not in RANGE_LIMITS:
                continue
            if value is not None:
                lo, hi = RANGE_LIMITS[field]
                if not (lo <= value <= hi):
                    logger.warning(
                        "Range violation: %s=%s (limits %s-%s)",
                        field,
                        value,
                        lo,
                        hi,
                    )
                    return False

        # 11. Dedup (in-memory)
        sequence = payload["sequence"]
        first_boot = bool(flags & FLAG_FIRST_BOOT)
        now_mono = time.monotonic()

        if first_boot:
            # Clear cache for this hive on first boot
            self._dedup_cache.pop(hive_id, None)

        hive_cache = self._dedup_cache.setdefault(hive_id, {})

        if sequence in hive_cache:
            cached_time = hive_cache[sequence]
            if now_mono - cached_time < DEDUP_TTL_SECONDS:
                logger.debug(
                    "Dedup hit: hive=%d seq=%d", hive_id, sequence
                )
                return False

        # Add to cache
        hive_cache[sequence] = now_mono

        # Evict expired entries, then cap at max
        self._evict_dedup_cache(hive_id, now_mono)

        # 12. DB insert (INSERT OR IGNORE for MQTT redelivery dedup via unique index)
        ingested_at = utc_now()
        sender_mac = payload.get("sender_mac", "")

        async with AsyncSession(self.engine) as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "INSERT OR IGNORE INTO sensor_readings "
                        "(hive_id, observed_at, ingested_at, weight_kg, temp_c, "
                        "humidity_pct, pressure_hpa, battery_v, sequence, flags, sender_mac) "
                        "VALUES (:hive_id, :observed_at, :ingested_at, :weight_kg, :temp_c, "
                        ":humidity_pct, :pressure_hpa, :battery_v, :sequence, :flags, :sender_mac)"
                    ),
                    {
                        "hive_id": hive_id,
                        "observed_at": observed_at,
                        "ingested_at": ingested_at,
                        "weight_kg": weight_kg,
                        "temp_c": temp_c,
                        "humidity_pct": humidity_pct,
                        "pressure_hpa": pressure_hpa,
                        "battery_v": battery_v,
                        "sequence": sequence,
                        "flags": flags,
                        "sender_mac": sender_mac,
                    },
                )

                if result.rowcount == 0:
                    # Duplicate caught by DB unique index
                    logger.debug(
                        "DB dedup: hive=%d seq=%d observed_at=%s",
                        hive_id,
                        sequence,
                        observed_at,
                    )
                    return False

                # Get the inserted reading ID
                reading_id_result = await session.execute(text("SELECT last_insert_rowid()"))
                reading_id = reading_id_result.scalar()

                # 13. Update last_seen_at (monotonic advance)
                await session.execute(
                    text(
                        "UPDATE hives SET last_seen_at = :observed_at "
                        "WHERE id = :hive_id "
                        "AND (last_seen_at IS NULL OR last_seen_at < :observed_at)"
                    ),
                    {"observed_at": observed_at, "hive_id": hive_id},
                )

        # 14. Trigger alert engine
        await self.alert_engine.check_reading(hive_id, reading_id, converted)

        return True

    def _evict_dedup_cache(self, hive_id: int, now_mono: float) -> None:
        """Sweep expired entries from a hive's dedup cache, then cap at max size."""
        hive_cache = self._dedup_cache.get(hive_id)
        if hive_cache is None:
            return

        # Remove expired entries
        expired = [
            seq
            for seq, ts in hive_cache.items()
            if now_mono - ts >= DEDUP_TTL_SECONDS
        ]
        for seq in expired:
            del hive_cache[seq]

        # Cap at max entries (evict oldest first)
        if len(hive_cache) > DEDUP_MAX_PER_HIVE:
            sorted_entries = sorted(hive_cache.items(), key=lambda x: x[1])
            excess = len(hive_cache) - DEDUP_MAX_PER_HIVE
            for seq, _ in sorted_entries[:excess]:
                del hive_cache[seq]
