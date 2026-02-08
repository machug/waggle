"""Bridge service: processes raw COBS-encoded serial frames into MQTT-ready JSON dicts."""

from waggle.utils.cobs import CobsDecodeError, cobs_decode
from waggle.utils.payload import PayloadError, deserialize_payload
from waggle.utils.timestamps import utc_now

_FRAME_LENGTH = 38  # 6 bytes MAC + 32 bytes payload


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

        # 2. Validate frame length
        if len(decoded) != _FRAME_LENGTH:
            return None

        # 3. Extract MAC (first 6 bytes) and format as uppercase colon-separated hex
        mac_bytes = decoded[:6]
        mac_str = ":".join(f"{b:02X}" for b in mac_bytes)

        # 4. Extract payload (bytes 6-37) — must be bytes for deserialize_payload
        payload_bytes = bytes(decoded[6:])

        # 5-6. Deserialize payload (includes CRC-8 validation internally)
        try:
            payload = deserialize_payload(payload_bytes)
        except PayloadError:
            return None

        # 7. Set observed_at to current UTC time
        observed_at = utc_now()

        # 8. Build MQTT topic and JSON dict
        topic = f"waggle/{payload['hive_id']}/sensors"

        msg = {
            "schema_version": 1,
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

        # 9. Return topic and dict
        return topic, msg
