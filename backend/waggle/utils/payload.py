"""Binary payload deserializer for ESP32 sensor frames (32-byte Phase 1, 48-byte Phase 2)."""

import struct

from waggle.utils.crc8 import crc8


class PayloadError(Exception):
    pass


# Common data fields (bytes 0-16, 17 bytes):
# hive_id(u8), msg_type(u8), seq(u16), weight(i32), temp(i16),
# hum(u16), pres(u16), batt(u16), flags(u8)
_COMMON_FORMAT = "<BBHihHHHB"

# Phase 2 traffic fields (bytes 18-27, 10 bytes):
# bees_in(u16), bees_out(u16), period_ms(u32), lane_mask(u8), stuck_mask(u8)
_TRAFFIC_FORMAT = "<HHIBB"

_VALID_LENGTHS = {32, 48}
_MSG_TYPE_FOR_LENGTH = {32: 0x01, 48: 0x02}


def deserialize_payload(data: bytes) -> dict:
    if len(data) not in _VALID_LENGTHS:
        raise PayloadError(
            f"Expected 32 or 48-byte payload, got {len(data)} bytes length"
        )

    # Verify CRC-8 over bytes 0-16 (same for both phases)
    expected_crc = crc8(data[:17])
    actual_crc = data[17]
    if expected_crc != actual_crc:
        raise PayloadError(
            f"CRC mismatch: expected 0x{expected_crc:02X}, got 0x{actual_crc:02X}"
        )

    fields = struct.unpack_from(_COMMON_FORMAT, data, 0)
    (hive_id, msg_type, sequence, weight_g, temp_c_x100,
     humidity_x100, pressure_hpa_x10, battery_mv, flags) = fields

    expected_msg_type = _MSG_TYPE_FOR_LENGTH[len(data)]
    if msg_type != expected_msg_type:
        raise PayloadError(
            f"Expected msg_type 0x{expected_msg_type:02X} for {len(data)}-byte payload, "
            f"got 0x{msg_type:02X}"
        )

    result = {
        "hive_id": hive_id,
        "msg_type": msg_type,
        "sequence": sequence,
        "weight_g": weight_g,
        "temp_c_x100": temp_c_x100,
        "humidity_x100": humidity_x100,
        "pressure_hpa_x10": pressure_hpa_x10,
        "battery_mv": battery_mv,
        "flags": flags,
    }

    if len(data) == 48:
        traffic = struct.unpack_from(_TRAFFIC_FORMAT, data, 18)
        bees_in, bees_out, period_ms, lane_mask, stuck_mask = traffic
        result.update({
            "bees_in": bees_in,
            "bees_out": bees_out,
            "period_ms": period_ms,
            "lane_mask": lane_mask,
            "stuck_mask": stuck_mask,
        })

    return result
