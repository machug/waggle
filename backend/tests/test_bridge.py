"""Tests for bridge service (serial frame processing)."""

import struct

import pytest

from waggle.services.bridge import BridgeProcessor
from waggle.utils.cobs import cobs_encode
from waggle.utils.crc8 import crc8


def _build_frame(
    mac=b"\xAA\xBB\xCC\xDD\xEE\xFF",
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
    """Build a valid COBS-encoded frame (MAC + payload)."""
    # Build 32-byte payload
    data = struct.pack(
        "<BBHihHHHB",
        hive_id, msg_type, sequence,
        weight_g, temp_c_x100, humidity_x100,
        pressure_hpa_x10, battery_mv, flags,
    )
    crc_val = crc8(data[:17])
    payload = data + bytes([crc_val]) + bytes(14)  # 17 + 1 + 14 = 32

    # Concatenate MAC (6 bytes) + payload (32 bytes) = 38 bytes
    frame_data = mac + payload
    assert len(frame_data) == 38

    # COBS encode
    return cobs_encode(frame_data)


@pytest.fixture
def processor():
    return BridgeProcessor()


def test_valid_frame(processor):
    encoded = _build_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    topic, msg = result
    assert topic == "waggle/1/sensors"
    assert msg["schema_version"] == 1
    assert msg["hive_id"] == 1
    assert msg["msg_type"] == 1
    assert msg["sequence"] == 1024
    assert msg["weight_g"] == 32120
    assert msg["temp_c_x100"] == 3645
    assert msg["humidity_x100"] == 5120
    assert msg["pressure_hpa_x10"] == 10132
    assert msg["battery_mv"] == 3710
    assert msg["flags"] == 0
    assert msg["sender_mac"] == "AA:BB:CC:DD:EE:FF"
    assert "observed_at" in msg


def test_mac_normalized_uppercase(processor):
    encoded = _build_frame(mac=b"\xaa\xbb\xcc\xdd\xee\xff")
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    assert msg["sender_mac"] == "AA:BB:CC:DD:EE:FF"


def test_observed_at_format(processor):
    import re
    encoded = _build_frame()
    result = processor.process_frame(encoded)
    _, msg = result
    # Should match YYYY-MM-DDTHH:MM:SS.mmmZ
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", msg["observed_at"])


def test_mqtt_topic(processor):
    encoded = _build_frame(hive_id=42)
    result = processor.process_frame(encoded)
    assert result is not None
    topic, _ = result
    assert topic == "waggle/42/sensors"


def test_bad_cobs(processor):
    """Invalid COBS data should return None."""
    result = processor.process_frame(b"")
    assert result is None


def test_wrong_frame_length(processor):
    """Frame that decodes to != 38 bytes should return None."""
    # Encode a 10-byte frame (not 38)
    encoded = cobs_encode(bytes(10))
    result = processor.process_frame(encoded)
    assert result is None


def test_bad_crc(processor):
    """Corrupted CRC should return None."""
    # Build valid frame, then corrupt the CRC byte
    mac = b"\xAA\xBB\xCC\xDD\xEE\xFF"
    data = struct.pack("<BBHihHHHB", 1, 0x01, 1024, 32120, 3645, 5120, 10132, 3710, 0)
    crc_val = crc8(data[:17])
    payload = data + bytes([crc_val ^ 0xFF]) + bytes(14)  # Corrupt CRC
    frame_data = mac + payload
    encoded = cobs_encode(frame_data)
    result = processor.process_frame(encoded)
    assert result is None


def test_flags_preserved(processor):
    encoded = _build_frame(flags=0b00101001)
    result = processor.process_frame(encoded)
    _, msg = result
    assert msg["flags"] == 0b00101001
