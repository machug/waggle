"""Tests for bridge service (serial frame processing)."""

import struct

import pytest

from waggle.services.bridge import BridgeProcessor
from waggle.utils.cobs import cobs_encode
from waggle.utils.crc8 import crc8

# ---------------------------------------------------------------------------
# Phase 1 (38-byte frame) helper
# ---------------------------------------------------------------------------


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
    """Build a valid COBS-encoded Phase 1 frame (6 MAC + 32 payload = 38 bytes)."""
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


# ---------------------------------------------------------------------------
# Phase 2 (54-byte frame) helper
# ---------------------------------------------------------------------------

_TRAFFIC_FIELDS = ("bees_in", "bees_out", "period_ms", "lane_mask", "stuck_mask")


def _build_phase2_frame(
    mac=b"\xAA\xBB\xCC\xDD\xEE\xFF",
    hive_id=1,
    sequence=42,
    weight_g=50000,
    temp_c_x100=2500,
    humidity_x100=6000,
    pressure_hpa_x10=10130,
    battery_mv=3700,
    flags=0,
    bees_in=100,
    bees_out=150,
    period_ms=60000,
    lane_mask=15,
    stuck_mask=0,
) -> bytes:
    """Build a valid COBS-encoded Phase 2 frame (6 MAC + 48 payload = 54 bytes)."""
    # Bytes 0-16: common data fields (17 bytes)
    data = struct.pack(
        "<BBHihHHHB",
        hive_id, 0x02, sequence,
        weight_g, temp_c_x100, humidity_x100,
        pressure_hpa_x10, battery_mv, flags,
    )
    assert len(data) == 17
    # Byte 17: CRC over bytes 0-16
    crc_val = crc8(data)
    # Bytes 18-27: traffic fields (10 bytes)
    traffic = struct.pack("<HHIBB", bees_in, bees_out, period_ms, lane_mask, stuck_mask)
    # Build 48-byte payload: 17 data + 1 CRC + 10 traffic + 20 reserved
    payload = data + bytes([crc_val]) + traffic + b"\x00" * (48 - 18 - len(traffic))
    assert len(payload) == 48

    # Concatenate MAC (6 bytes) + payload (48 bytes) = 54 bytes
    frame_data = mac + payload
    assert len(frame_data) == 54

    # COBS encode
    return cobs_encode(frame_data)


@pytest.fixture
def processor():
    return BridgeProcessor()


# ---------------------------------------------------------------------------
# Phase 1 regression tests
# ---------------------------------------------------------------------------


def test_valid_frame(processor):
    """Phase 1 (38-byte) frame still works after Phase 2 changes."""
    encoded = _build_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    topic, msg = result
    assert topic == "waggle/1/sensors"
    assert msg["schema_version"] == 2
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
    """Frame that decodes to neither 38 nor 54 bytes should return None."""
    # Encode a 10-byte frame
    encoded = cobs_encode(bytes(10))
    result = processor.process_frame(encoded)
    assert result is None


def test_wrong_frame_length_45(processor):
    """Frame of 45 bytes (between 38 and 54) should be rejected."""
    encoded = cobs_encode(bytes(45))
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


# ---------------------------------------------------------------------------
# Phase 1 traffic field absence
# ---------------------------------------------------------------------------


def test_phase1_no_traffic_fields(processor):
    """Phase 1 (msg_type=1) output must NOT contain traffic fields."""
    encoded = _build_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    for field in _TRAFFIC_FIELDS:
        assert field not in msg, f"Traffic field '{field}' should not be in Phase 1 output"


# ---------------------------------------------------------------------------
# Phase 2 (54-byte frame) tests
# ---------------------------------------------------------------------------


def test_phase2_valid_frame(processor):
    """Bridge accepts 54-byte COBS frame and outputs traffic fields."""
    encoded = _build_phase2_frame(
        bees_in=210, bees_out=245, period_ms=60000, lane_mask=0x0F, stuck_mask=3,
    )
    result = processor.process_frame(encoded)
    assert result is not None
    topic, msg = result
    assert topic == "waggle/1/sensors"
    assert msg["msg_type"] == 2
    assert msg["hive_id"] == 1
    assert msg["weight_g"] == 50000
    assert msg["bees_in"] == 210
    assert msg["bees_out"] == 245
    assert msg["period_ms"] == 60000
    assert msg["lane_mask"] == 0x0F
    assert msg["stuck_mask"] == 3


def test_phase2_schema_version(processor):
    """Phase 2 output should have schema_version=2."""
    encoded = _build_phase2_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    assert msg["schema_version"] == 2


def test_phase1_schema_version(processor):
    """Phase 1 output should also have schema_version=2 (protocol upgrade)."""
    encoded = _build_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    assert msg["schema_version"] == 2


def test_phase2_common_sensor_fields(processor):
    """Phase 2 frames include all common sensor fields alongside traffic fields."""
    encoded = _build_phase2_frame(
        hive_id=5, sequence=999, weight_g=-1000, temp_c_x100=-500,
        humidity_x100=9500, pressure_hpa_x10=9800, battery_mv=4200, flags=0x0F,
    )
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    assert msg["hive_id"] == 5
    assert msg["sequence"] == 999
    assert msg["weight_g"] == -1000
    assert msg["temp_c_x100"] == -500
    assert msg["humidity_x100"] == 9500
    assert msg["pressure_hpa_x10"] == 9800
    assert msg["battery_mv"] == 4200
    assert msg["flags"] == 0x0F


def test_phase2_traffic_fields_present(processor):
    """Phase 2 output must contain all traffic fields."""
    encoded = _build_phase2_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    for field in _TRAFFIC_FIELDS:
        assert field in msg, f"Traffic field '{field}' missing from Phase 2 output"


def test_phase2_mqtt_topic(processor):
    """Phase 2 frames produce the correct MQTT topic."""
    encoded = _build_phase2_frame(hive_id=7)
    result = processor.process_frame(encoded)
    assert result is not None
    topic, _ = result
    assert topic == "waggle/7/sensors"


def test_phase2_bad_crc(processor):
    """Phase 2 frame with corrupted CRC should return None."""
    mac = b"\xAA\xBB\xCC\xDD\xEE\xFF"
    data = struct.pack("<BBHihHHHB", 1, 0x02, 42, 50000, 2500, 6000, 10130, 3700, 0)
    crc_val = crc8(data[:17])
    traffic = struct.pack("<HHIBB", 100, 150, 60000, 15, 0)
    payload = data + bytes([crc_val ^ 0xFF]) + traffic + b"\x00" * 20  # Corrupt CRC
    frame_data = mac + payload
    assert len(frame_data) == 54
    encoded = cobs_encode(frame_data)
    result = processor.process_frame(encoded)
    assert result is None


def test_phase2_observed_at_format(processor):
    """Phase 2 output includes properly formatted observed_at."""
    import re
    encoded = _build_phase2_frame()
    result = processor.process_frame(encoded)
    assert result is not None
    _, msg = result
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", msg["observed_at"])
