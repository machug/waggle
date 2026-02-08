"""Binary payload deserializer for 32-byte ESP32 sensor frames."""

import struct

from waggle.utils.crc8 import crc8


class PayloadError(Exception):
    pass


# Phase 1 payload: 32 bytes, little-endian
# Offsets 0-16: data fields (17 bytes)
# Offset 17: CRC-8 over bytes 0-16
# Offsets 18-31: reserved (14 bytes)
_PHASE1_FORMAT = "<BBHihHHHB"  # 17 bytes: hive_id, msg_type, seq, weight, temp, hum, pres, batt, flags


def deserialize_payload(data: bytes) -> dict:
    if len(data) != 32:
        raise PayloadError(f"Expected 32-byte payload, got {len(data)} bytes length")

    # Verify CRC-8 over bytes 0-16
    expected_crc = crc8(data[:17])
    actual_crc = data[17]
    if expected_crc != actual_crc:
        raise PayloadError(
            f"CRC mismatch: expected 0x{expected_crc:02X}, got 0x{actual_crc:02X}"
        )

    fields = struct.unpack_from(_PHASE1_FORMAT, data, 0)
    hive_id, msg_type, sequence, weight_g, temp_c_x100, humidity_x100, pressure_hpa_x10, battery_mv, flags = fields

    if msg_type != 0x01:
        raise PayloadError(f"Unknown msg_type 0x{msg_type:02X}")

    return {
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
