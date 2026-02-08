"""Tests for 32-byte sensor payload deserializer."""

import struct

import pytest

from waggle.utils.crc8 import crc8
from waggle.utils.payload import PayloadError, deserialize_payload


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
