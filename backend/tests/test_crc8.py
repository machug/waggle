"""Tests for CRC-8 (poly 0x07, init 0x00)."""

from waggle.utils.crc8 import crc8


def test_empty():
    assert crc8(b"") == 0x00


def test_known_vector_123456789():
    """Standard CRC-8 test vector: ASCII '123456789' -> 0xF4."""
    assert crc8(b"123456789") == 0xF4


def test_single_byte():
    assert crc8(b"\x00") == 0x00
    assert crc8(b"\x01") == 0x07


def test_all_zeros():
    assert crc8(bytes(17)) == 0x00


def test_consistency():
    """Same input always produces same output."""
    data = bytes(range(17))
    assert crc8(data) == crc8(data)
