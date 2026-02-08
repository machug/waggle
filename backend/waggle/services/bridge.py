"""Bridge service: processes raw COBS-encoded serial frames into MQTT-ready JSON dicts."""

import logging

from waggle.utils.cobs import CobsDecodeError, cobs_decode
from waggle.utils.payload import PayloadError, deserialize_payload
from waggle.utils.timestamps import utc_now

logger = logging.getLogger(__name__)

_MAC_LENGTH = 6
_VALID_FRAME_LENGTHS = {
    38,  # 6 MAC + 32 payload (Phase 1, msg_type=0x01)
    54,  # 6 MAC + 48 payload (Phase 2, msg_type=0x02)
}

_TRAFFIC_FIELDS = ("bees_in", "bees_out", "period_ms", "lane_mask", "stuck_mask")


class BridgeProcessor:
    """Processes raw COBS-encoded serial frames into MQTT-ready JSON dicts."""

    def process_frame(self, raw_frame: bytes) -> tuple[str, dict] | None:
        """Process a single COBS-encoded frame.

        Returns (topic, payload_dict) or None if frame is invalid.
        """
        # 1. COBS decode
        try:
            decoded = cobs_decode(raw_frame)
        except CobsDecodeError:
            return None

        # 2. Validate frame length (38 for Phase 1, 54 for Phase 2)
        if len(decoded) not in _VALID_FRAME_LENGTHS:
            logger.warning(
                "Unexpected frame length %d bytes (expected 38 or 54)",
                len(decoded),
            )
            return None

        # 3. Extract MAC (first 6 bytes) and format as uppercase colon-separated hex
        mac_bytes = decoded[:_MAC_LENGTH]
        mac_str = ":".join(f"{b:02X}" for b in mac_bytes)

        # 4. Extract payload (remaining bytes after MAC)
        payload_bytes = bytes(decoded[_MAC_LENGTH:])

        # 5-6. Deserialize payload (includes CRC-8 and msg_type validation internally)
        try:
            payload = deserialize_payload(payload_bytes)
        except PayloadError:
            return None

        # 7. Set observed_at to current UTC time
        observed_at = utc_now()

        # 8. Build MQTT topic and JSON dict
        topic = f"waggle/{payload['hive_id']}/sensors"

        msg = {
            "schema_version": 2,
            "hive_id": payload["hive_id"],
            "msg_type": payload["msg_type"],
            "sequence": payload["sequence"],
            "weight_g": payload["weight_g"],
            "temp_c_x100": payload["temp_c_x100"],
            "humidity_x100": payload["humidity_x100"],
            "pressure_hpa_x10": payload["pressure_hpa_x10"],
            "battery_mv": payload["battery_mv"],
            "flags": payload["flags"],
            "sender_mac": mac_str,
            "observed_at": observed_at,
        }

        # 9. Include traffic fields for Phase 2 (msg_type=0x02) payloads
        if payload["msg_type"] == 0x02:
            for field in _TRAFFIC_FIELDS:
                msg[field] = payload[field]

        # 10. Return topic and dict
        return topic, msg
