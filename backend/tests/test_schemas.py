"""Tests for Pydantic request/response schemas."""

import pytest
from pydantic import ValidationError

from waggle.schemas import (
    AlertAcknowledge,
    HiveCreate,
    HiveOut,
    HiveUpdate,
    LatestReading,
    LatestTrafficOut,
    TrafficAggregateOut,
    TrafficRecordOut,
    TrafficResponse,
    TrafficSummaryOut,
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


class TestLatestTrafficOut:
    def test_valid(self):
        t = LatestTrafficOut(
            observed_at="2026-02-08T12:00:00Z",
            bees_in=42,
            bees_out=38,
            net_out=-4,
            total_traffic=80,
        )
        assert t.bees_in == 42
        assert t.net_out == -4
        assert t.total_traffic == 80

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            LatestTrafficOut(
                observed_at="2026-02-08T12:00:00Z",
                bees_in=10,
                # bees_out missing
                net_out=0,
                total_traffic=10,
            )


class TestTrafficRecordOut:
    def test_valid(self):
        r = TrafficRecordOut(
            id=1,
            reading_id=100,
            hive_id=1,
            observed_at="2026-02-08T12:00:00Z",
            period_ms=60000,
            bees_in=12,
            bees_out=8,
            net_out=-4,
            total_traffic=20,
            lane_mask=0xFF,
            stuck_mask=0x00,
            flags=0,
        )
        assert r.id == 1
        assert r.period_ms == 60000
        assert r.lane_mask == 0xFF
        assert r.stuck_mask == 0

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            TrafficRecordOut(
                id=1,
                # reading_id missing
                hive_id=1,
                observed_at="2026-02-08T12:00:00Z",
                period_ms=60000,
                bees_in=0,
                bees_out=0,
                net_out=0,
                total_traffic=0,
                lane_mask=0,
                stuck_mask=0,
                flags=0,
            )


class TestTrafficAggregateOut:
    def test_valid(self):
        a = TrafficAggregateOut(
            period_start="2026-02-08T12:00:00Z",
            period_end="2026-02-08T13:00:00Z",
            reading_count=60,
            sum_bees_in=720,
            sum_bees_out=680,
            sum_net_out=-40,
            sum_total_traffic=1400,
            avg_bees_in_per_min=12.0,
            avg_bees_out_per_min=11.33,
        )
        assert a.reading_count == 60
        assert a.avg_bees_in_per_min == 12.0
        assert a.avg_bees_out_per_min == pytest.approx(11.33)


class TestTrafficResponse:
    def test_with_raw_records(self):
        record = TrafficRecordOut(
            id=1,
            reading_id=100,
            hive_id=1,
            observed_at="2026-02-08T12:00:00Z",
            period_ms=60000,
            bees_in=5,
            bees_out=3,
            net_out=-2,
            total_traffic=8,
            lane_mask=0xFF,
            stuck_mask=0,
            flags=0,
        )
        resp = TrafficResponse(
            items=[record],
            interval="raw",
            total=1,
            limit=100,
            offset=0,
        )
        assert resp.interval == "raw"
        assert len(resp.items) == 1
        assert resp.total == 1

    def test_with_aggregates(self):
        agg = TrafficAggregateOut(
            period_start="2026-02-08T00:00:00Z",
            period_end="2026-02-09T00:00:00Z",
            reading_count=1440,
            sum_bees_in=5000,
            sum_bees_out=4800,
            sum_net_out=-200,
            sum_total_traffic=9800,
            avg_bees_in_per_min=3.47,
            avg_bees_out_per_min=3.33,
        )
        resp = TrafficResponse(
            items=[agg],
            interval="daily",
            total=1,
            limit=100,
            offset=0,
        )
        assert resp.interval == "daily"

    def test_empty_items(self):
        resp = TrafficResponse(
            items=[],
            interval="hourly",
            total=0,
            limit=100,
            offset=0,
        )
        assert resp.items == []
        assert resp.total == 0


class TestTrafficSummaryOut:
    def test_valid_all_fields(self):
        s = TrafficSummaryOut(
            date="2026-02-08",
            total_in=5000,
            total_out=4800,
            net_out=-200,
            total_traffic=9800,
            peak_hour=14,
            rolling_7d_avg_total=8500,
            activity_score=72,
        )
        assert s.date == "2026-02-08"
        assert s.peak_hour == 14
        assert s.activity_score == 72

    def test_nullable_fields(self):
        s = TrafficSummaryOut(
            date="2026-02-08",
            total_in=100,
            total_out=90,
            net_out=-10,
            total_traffic=190,
            peak_hour=None,
            rolling_7d_avg_total=None,
            activity_score=None,
        )
        assert s.peak_hour is None
        assert s.rolling_7d_avg_total is None
        assert s.activity_score is None


class TestHiveOutTrafficFields:
    def test_hive_out_without_traffic(self):
        h = HiveOut(
            id=1,
            name="Hive Alpha",
            location=None,
            notes=None,
            sender_mac=None,
            last_seen_at=None,
            created_at="2026-01-01T00:00:00Z",
        )
        assert h.latest_traffic is None
        assert h.activity_score_today is None

    def test_hive_out_with_traffic(self):
        traffic = LatestTrafficOut(
            observed_at="2026-02-08T12:00:00Z",
            bees_in=42,
            bees_out=38,
            net_out=-4,
            total_traffic=80,
        )
        h = HiveOut(
            id=1,
            name="Hive Alpha",
            location="Garden",
            notes=None,
            sender_mac="AA:BB:CC:DD:EE:FF",
            last_seen_at="2026-02-08T12:00:00Z",
            created_at="2026-01-01T00:00:00Z",
            latest_traffic=traffic,
            activity_score_today=72,
        )
        assert h.latest_traffic is not None
        assert h.latest_traffic.bees_in == 42
        assert h.activity_score_today == 72
