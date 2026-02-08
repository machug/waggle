"""Tests for COBS (Consistent Overhead Byte Stuffing) decoder."""

import pytest

from waggle.utils.cobs import CobsDecodeError, cobs_decode, cobs_encode


def test_empty_frame():
    """Empty input should raise."""
    with pytest.raises(CobsDecodeError):
        cobs_decode(b"")


def test_single_overhead_byte():
    """Single overhead byte (0x01) decodes to empty bytes."""
    assert cobs_decode(b"\x01") == b""


def test_no_zeros_in_data():
    """Data with no zero bytes: b'\\x01\\x02\\x03'."""
    encoded = cobs_encode(b"\x01\x02\x03")
    assert cobs_decode(encoded) == b"\x01\x02\x03"


def test_single_zero():
    """Data is just a zero byte: b'\\x00'."""
    encoded = cobs_encode(b"\x00")
    assert cobs_decode(encoded) == b"\x00"


def test_all_zeros():
    """Three zero bytes."""
    encoded = cobs_encode(b"\x00\x00\x00")
    assert cobs_decode(encoded) == b"\x00\x00\x00"


def test_mixed():
    """Mixed data with zeros and non-zeros."""
    data = b"\x01\x00\x02\x03\x00\x04"
    encoded = cobs_encode(data)
    assert cobs_decode(encoded) == data


def test_round_trip_38_bytes():
    """38-byte frame (6 MAC + 32 payload) should round-trip correctly."""
    data = bytes(range(38))
    encoded = cobs_encode(data)
    assert cobs_decode(encoded) == data


def test_round_trip_with_zeros():
    """Data with multiple zero bytes should round-trip."""
    data = b"\x00" * 10
    assert cobs_decode(cobs_encode(data)) == data


def test_round_trip_max_block():
    """254 non-zero bytes (max block size) should round-trip."""
    data = bytes(range(1, 255))  # 254 bytes, no zeros
    assert cobs_decode(cobs_encode(data)) == data


def test_round_trip_255_bytes():
    """255 non-zero bytes (forces block split) should round-trip."""
    data = bytes([i % 254 + 1 for i in range(255)])
    assert cobs_decode(cobs_encode(data)) == data
