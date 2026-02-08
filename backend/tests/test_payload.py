"""Tests for sensor payload deserializer (32-byte Phase 1, 48-byte Phase 2)."""

import struct

import pytest

from waggle.utils.crc8 import crc8
from waggle.utils.payload import PayloadError, deserialize_payload

# ---------------------------------------------------------------------------
# Phase 1 (32-byte) helper
# ---------------------------------------------------------------------------


def _build_payload(
    hive_id=1,
    msg_type=0x01,
    sequence=1024,
    weight_g=32120,
    temp_c_x100=3645,
    humidity_x100=5120,
    pressure_hpa_x10=10132,
    battery_mv=3710,
    flags=0,
) -> bytes:
    """Build a valid 32-byte Phase 1 payload with correct CRC."""
    data = struct.pack(
        "<BBHihHHHB",
        hive_id,
        msg_type,
        sequence,
        weight_g,
        temp_c_x100,
        humidity_x100,
        pressure_hpa_x10,
        battery_mv,
        flags,
    )
    # data is 17 bytes (0-16), CRC at byte 17
    crc = crc8(data[:17])
    return data + bytes([crc]) + bytes(14)  # 17 + 1 + 14 = 32


# ---------------------------------------------------------------------------
# Phase 2 (48-byte) helper
# ---------------------------------------------------------------------------


def _build_phase2_payload(
    hive_id=1,
    sequence=42,
    weight_g=50000,
    temp_x100=2500,
    humidity_x100=6000,
    pressure_x10=10130,
    battery_mv=3700,
    flags=0,
    bees_in=100,
    bees_out=150,
    period_ms=60000,
    lane_mask=15,
    stuck_mask=0,
) -> bytes:
    """Build a valid 48-byte Phase 2 payload."""
    # Bytes 0-16: data fields (same struct format as Phase 1)
    data = struct.pack(
        "<BBHihHHHB",
        hive_id,
        0x02,
        sequence,
        weight_g,
        temp_x100,
        humidity_x100,
        pressure_x10,
        battery_mv,
        flags,
    )
    assert len(data) == 17
    # Byte 17: CRC over bytes 0-16
    crc_val = crc8(data)
    # Bytes 18-27: traffic fields
    traffic = struct.pack("<HHIBB", bees_in, bees_out, period_ms, lane_mask, stuck_mask)
    # Build 48-byte payload: 17 data + 1 CRC + 10 traffic + 20 reserved
    payload = data + bytes([crc_val]) + traffic + b"\x00" * (48 - 18 - len(traffic))
    assert len(payload) == 48
    return payload


# ---------------------------------------------------------------------------
# Phase 1 tests (existing)
# ---------------------------------------------------------------------------


def test_valid_payload():
    raw = _build_payload()
    p = deserialize_payload(raw)
    assert p["hive_id"] == 1
    assert p["msg_type"] == 0x01
    assert p["sequence"] == 1024
    assert p["weight_g"] == 32120
    assert p["temp_c_x100"] == 3645
    assert p["humidity_x100"] == 5120
    assert p["pressure_hpa_x10"] == 10132
    assert p["battery_mv"] == 3710
    assert p["flags"] == 0


def test_bad_crc():
    raw = bytearray(_build_payload())
    raw[17] ^= 0xFF  # corrupt CRC
    with pytest.raises(PayloadError, match="CRC"):
        deserialize_payload(bytes(raw))


def test_wrong_length():
    with pytest.raises(PayloadError, match="length"):
        deserialize_payload(bytes(16))


def test_wrong_msg_type():
    raw = bytearray(_build_payload(msg_type=0x99))
    # Fix CRC for the corrupted msg_type
    raw[17] = crc8(bytes(raw[:17]))
    with pytest.raises(PayloadError, match="msg_type"):
        deserialize_payload(bytes(raw))


def test_flags_parsed():
    raw = _build_payload(flags=0b00101001)  # LOW_BATTERY + HX711_ERROR + FIRST_BOOT
    p = deserialize_payload(raw)
    assert p["flags"] == 0b00101001


# ---------------------------------------------------------------------------
# Phase 2 tests (new)
# ---------------------------------------------------------------------------


def test_deserialize_phase2_basic():
    payload = _build_phase2_payload(bees_in=210, bees_out=245, period_ms=60000)
    result = deserialize_payload(payload)
    assert result["msg_type"] == 2
    assert result["hive_id"] == 1
    assert result["weight_g"] == 50000
    assert result["bees_in"] == 210
    assert result["bees_out"] == 245
    assert result["period_ms"] == 60000
    assert result["lane_mask"] == 15
    assert result["stuck_mask"] == 0


def test_deserialize_phase2_with_stuck_mask():
    payload = _build_phase2_payload(stuck_mask=3)
    result = deserialize_payload(payload)
    assert result["stuck_mask"] == 3


def test_deserialize_phase2_wrong_msg_type():
    """48-byte payload with msg_type=0x01 should fail."""
    payload = bytearray(_build_phase2_payload())
    # Patch msg_type to 0x01
    payload[1] = 0x01
    # Recalculate CRC
    payload[17] = crc8(bytes(payload[:17]))
    with pytest.raises(PayloadError, match="msg_type"):
        deserialize_payload(bytes(payload))


def test_deserialize_phase1_wrong_msg_type_0x02():
    """32-byte payload with msg_type=0x02 should fail."""
    raw = bytearray(_build_payload(msg_type=0x02))
    raw[17] = crc8(bytes(raw[:17]))
    with pytest.raises(PayloadError, match="msg_type"):
        deserialize_payload(bytes(raw))


def test_deserialize_invalid_length():
    with pytest.raises(PayloadError, match="length"):
        deserialize_payload(b"\x00" * 40)


def test_phase2_no_traffic_keys_in_phase1():
    """Phase 1 payloads must NOT contain traffic keys."""
    raw = _build_payload()
    result = deserialize_payload(raw)
    assert "bees_in" not in result
    assert "bees_out" not in result
    assert "period_ms" not in result
    assert "lane_mask" not in result
    assert "stuck_mask" not in result


def test_phase2_all_sensor_fields():
    """Phase 2 payloads include all Phase 1 sensor fields."""
    payload = _build_phase2_payload(
        hive_id=3, sequence=999, weight_g=-1000, temp_x100=-500,
        humidity_x100=9500, pressure_x10=9800, battery_mv=4200, flags=0x0F,
    )
    result = deserialize_payload(payload)
    assert result["hive_id"] == 3
    assert result["sequence"] == 999
    assert result["weight_g"] == -1000
    assert result["temp_c_x100"] == -500
    assert result["humidity_x100"] == 9500
    assert result["pressure_hpa_x10"] == 9800
    assert result["battery_mv"] == 4200
    assert result["flags"] == 0x0F


def test_phase2_max_bees():
    """Traffic counters at max uint16 value."""
    payload = _build_phase2_payload(bees_in=65535, bees_out=65535)
    result = deserialize_payload(payload)
    assert result["bees_in"] == 65535
    assert result["bees_out"] == 65535


def test_phase2_bad_crc():
    """Phase 2 payloads with bad CRC should fail."""
    payload = bytearray(_build_phase2_payload())
    payload[17] ^= 0xFF
    with pytest.raises(PayloadError, match="CRC"):
        deserialize_payload(bytes(payload))
