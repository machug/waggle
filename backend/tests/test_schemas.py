"""Tests for Pydantic request/response schemas."""

import pytest
from pydantic import ValidationError

from waggle.schemas import (
    AlertAcknowledge,
    AlertOut,
    CameraNodeCreate,
    DetectionOut,
    HiveCreate,
    HiveOut,
    HiveUpdate,
    InspectionIn,
    LatestReading,
    LatestTrafficOut,
    PhotoOutLocal,
    SyncStatusOut,
    TrafficAggregateOut,
    TrafficRecordOut,
    TrafficResponse,
    TrafficSummaryOut,
    VarroaSummaryOut,
    WebhookPayload,
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


class TestCameraNodeCreate:
    def test_valid(self):
        c = CameraNodeCreate(device_id="cam-hive01-a", hive_id=1, api_key="a" * 32)
        assert c.device_id == "cam-hive01-a"

    def test_device_id_invalid_chars(self):
        with pytest.raises(ValidationError):
            CameraNodeCreate(device_id="cam hive", hive_id=1, api_key="a" * 32)

    def test_api_key_too_short(self):
        with pytest.raises(ValidationError):
            CameraNodeCreate(device_id="cam-1", hive_id=1, api_key="short")


class TestPhotoOutLocal:
    def test_valid(self):
        p = PhotoOutLocal(
            id=1,
            hive_id=1,
            device_id="cam-1",
            boot_id=5,
            captured_at="2026-02-08T12:00:00.000Z",
            captured_at_source="device_ntp",
            sequence=1,
            local_image_url="http://pi:8000/api/photos/1/image?token=abc&expires=9999",
            local_image_expires_at=9999999999,
            file_size_bytes=50000,
            sha256="abc123",
            ml_status="pending",
            ml_attempts=0,
        )
        assert p.ml_status == "pending"

    def test_invalid_ml_status(self):
        with pytest.raises(ValidationError):
            PhotoOutLocal(
                id=1,
                hive_id=1,
                device_id="cam-1",
                boot_id=5,
                captured_at="2026-02-08T12:00:00.000Z",
                captured_at_source="device_ntp",
                sequence=1,
                local_image_url="http://pi:8000/api/photos/1/image",
                local_image_expires_at=9999999999,
                file_size_bytes=50000,
                sha256="abc123",
                ml_status="unknown",
                ml_attempts=0,
            )


class TestDetectionOut:
    def test_valid(self):
        d = DetectionOut(
            id=1,
            photo_id=1,
            hive_id=1,
            detected_at="2026-02-08T12:00:00.000Z",
            top_class="varroa",
            top_confidence=0.95,
            detections_json=[
                {"class": "varroa", "confidence": 0.95, "bbox": [10, 20, 30, 40]}
            ],
            varroa_count=3,
            pollen_count=0,
            wasp_count=0,
            bee_count=12,
            inference_ms=150,
            model_version="yolov8n-waggle-v1",
            model_hash="abc123",
        )
        assert d.top_class == "varroa"

    def test_invalid_class(self):
        with pytest.raises(ValidationError):
            DetectionOut(
                id=1,
                photo_id=1,
                hive_id=1,
                detected_at="2026-02-08T12:00:00.000Z",
                top_class="unknown_class",
                top_confidence=0.5,
                detections_json=[],
                varroa_count=0,
                pollen_count=0,
                wasp_count=0,
                bee_count=0,
                inference_ms=100,
                model_version="v1",
                model_hash="abc",
            )


class TestVarroaSummaryOut:
    def test_valid(self):
        v = VarroaSummaryOut(
            hive_id=1,
            current_ratio=2.5,
            trend_7d="rising",
            trend_slope=0.3,
            days_since_treatment=14,
        )
        assert v.treatment_threshold == 3.0

    def test_insufficient_data(self):
        v = VarroaSummaryOut(
            hive_id=1,
            current_ratio=None,
            trend_7d="insufficient_data",
            trend_slope=None,
            days_since_treatment=None,
        )
        assert v.trend_7d == "insufficient_data"


class TestInspectionIn:
    def test_valid(self):
        i = InspectionIn(
            hive_id=1,
            inspected_at="2026-02-08T12:00:00.000Z",
            queen_seen=True,
            brood_pattern="good",
        )
        assert i.queen_seen is True
        assert i.uuid is None

    def test_defaults(self):
        i = InspectionIn(hive_id=1, inspected_at="2026-02-08T12:00:00.000Z")
        assert i.queen_seen is False
        assert i.brood_pattern is None

    def test_invalid_brood_pattern(self):
        with pytest.raises(ValidationError):
            InspectionIn(
                hive_id=1,
                inspected_at="2026-02-08T12:00:00.000Z",
                brood_pattern="excellent",
            )


class TestWebhookPayload:
    def test_valid(self):
        w = WebhookPayload(
            alert_id=1,
            type="VARROA_DETECTED",
            severity="high",
            hive_id=1,
            hive_name="Hive Alpha",
            message="Varroa mites detected",
            observed_at="2026-02-08T12:00:00.000Z",
            created_at="2026-02-08T12:00:01.000Z",
        )
        assert w.details is None


class TestSyncStatusOut:
    def test_valid(self):
        s = SyncStatusOut(pending_rows=42, pending_files=7)
        assert s.last_push_at is None
        assert s.pending_rows == 42


class TestAlertOutPhase3:
    def test_phase3_fields(self):
        a = AlertOut(
            id=1,
            hive_id=1,
            type="VARROA_DETECTED",
            severity="high",
            message="Mites detected",
            observed_at="2026-02-08T12:00:00.000Z",
            acknowledged=False,
            acknowledged_at=None,
            acknowledged_by=None,
            created_at="2026-02-08T12:00:01.000Z",
            notified_at="2026-02-08T12:00:02.000Z",
            updated_at="2026-02-08T12:00:01.000Z",
            source="local",
            details_json='{"varroa_count": 5}',
        )
        assert a.source == "local"
        assert a.observed_at == "2026-02-08T12:00:00.000Z"
