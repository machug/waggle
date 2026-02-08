"""Tests for Pydantic request/response schemas."""

import pytest
from pydantic import ValidationError

from waggle.schemas import (
    AlertAcknowledge,
    AlertOut,
    AlertsResponse,
    HiveCreate,
    HiveOut,
    HiveUpdate,
    HivesResponse,
    LatestReading,
    ReadingOut,
    ReadingsResponse,
    HubStatusOut,
)


class TestHiveCreate:
    def test_valid(self):
        h = HiveCreate(id=1, name="Hive Alpha")
        assert h.id == 1
        assert h.location is None

    def test_id_out_of_range(self):
        with pytest.raises(ValidationError):
            HiveCreate(id=0, name="Bad")
        with pytest.raises(ValidationError):
            HiveCreate(id=251, name="Bad")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            HiveCreate(id=1, name="x" * 65)

    def test_mac_normalized_to_upper(self):
        h = HiveCreate(id=1, name="Test", sender_mac="aa:bb:cc:dd:ee:ff")
        assert h.sender_mac == "AA:BB:CC:DD:EE:FF"

    def test_mac_invalid_format(self):
        with pytest.raises(ValidationError):
            HiveCreate(id=1, name="Test", sender_mac="not-a-mac")


class TestHiveUpdate:
    def test_partial_update(self):
        u = HiveUpdate(name="New Name")
        assert u.name == "New Name"
        assert u.location is None

    def test_empty_is_valid(self):
        u = HiveUpdate()
        assert u.name is None


class TestLatestReading:
    def test_valid(self):
        r = LatestReading(
            weight_kg=32.12,
            temp_c=36.45,
            humidity_pct=51.2,
            pressure_hpa=1013.2,
            battery_v=3.71,
            observed_at="2026-02-07T18:21:04.123Z",
            flags=0,
        )
        assert r.weight_kg == 32.12

    def test_nullable_fields(self):
        r = LatestReading(
            weight_kg=None,
            temp_c=None,
            humidity_pct=None,
            pressure_hpa=None,
            battery_v=None,
            observed_at="2026-02-07T18:21:04.123Z",
            flags=8,
        )
        assert r.weight_kg is None


class TestAlertAcknowledge:
    def test_valid(self):
        a = AlertAcknowledge(acknowledged_by="beekeeper")
        assert a.acknowledged_by == "beekeeper"

    def test_optional(self):
        a = AlertAcknowledge()
        assert a.acknowledged_by is None
