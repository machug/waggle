"""Tests for Prometheus metrics definitions and heartbeat health utilities."""

import json
import os
import time

from waggle.health import (
    HeartbeatWriter,
    alerts_fired,
    api_request_duration,
    bridge_crc_failures,
    bridge_frames_received,
    check_service_health,
    mqtt_publish_failures,
    readings_dropped,
    readings_ingested,
    serial_reconnects,
)

# ---------------------------------------------------------------------------
# Prometheus metrics: verify they exist and have expected types/labels
# ---------------------------------------------------------------------------

class TestPrometheusMetrics:
    """Verify that Prometheus metric singletons are correctly defined."""

    def test_api_request_duration_is_histogram(self):
        assert api_request_duration._type == "histogram"

    def test_api_request_duration_labels(self):
        assert api_request_duration._labelnames == ("method", "path", "status")

    def test_bridge_frames_received_is_counter(self):
        assert bridge_frames_received._type == "counter"

    def test_bridge_crc_failures_is_counter(self):
        assert bridge_crc_failures._type == "counter"

    def test_mqtt_publish_failures_is_counter(self):
        assert mqtt_publish_failures._type == "counter"

    def test_serial_reconnects_is_counter(self):
        assert serial_reconnects._type == "counter"

    def test_readings_ingested_labels(self):
        assert readings_ingested._labelnames == ("hive_id",)

    def test_readings_dropped_labels(self):
        assert readings_dropped._labelnames == ("hive_id", "reason")

    def test_alerts_fired_labels(self):
        assert alerts_fired._labelnames == ("hive_id", "type")


# ---------------------------------------------------------------------------
# HeartbeatWriter.write_heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeatWriter:
    """Tests for atomic heartbeat file writing."""

    def test_write_creates_heartbeat_file(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat({"serial_connected": True})
        hb_file = tmp_path / "bridge.hb"
        assert hb_file.exists()

    def test_heartbeat_file_is_valid_json(self, tmp_path):
        hb = HeartbeatWriter("worker", str(tmp_path))
        hb.write_heartbeat({"mqtt_connected": True})
        data = json.loads((tmp_path / "worker.hb").read_text())
        assert isinstance(data, dict)

    def test_heartbeat_contains_required_fields(self, tmp_path):
        hb = HeartbeatWriter("api", str(tmp_path))
        hb.write_heartbeat({"requests_total": 42})
        data = json.loads((tmp_path / "api.hb").read_text())
        assert "pid" in data
        assert "uptime_sec" in data
        assert "ts" in data
        assert "details" in data

    def test_heartbeat_pid_is_current_process(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        data = json.loads((tmp_path / "bridge.hb").read_text())
        assert data["pid"] == os.getpid()

    def test_heartbeat_uptime_is_non_negative(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        data = json.loads((tmp_path / "bridge.hb").read_text())
        assert data["uptime_sec"] >= 0

    def test_heartbeat_ts_format(self, tmp_path):
        """Timestamp should be ISO-like with milliseconds and Z suffix."""
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        data = json.loads((tmp_path / "bridge.hb").read_text())
        ts = data["ts"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_heartbeat_details_passed_through(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        details = {"serial_connected": True, "frames_total": 12345}
        hb.write_heartbeat(details)
        data = json.loads((tmp_path / "bridge.hb").read_text())
        assert data["details"]["serial_connected"] is True
        assert data["details"]["frames_total"] == 12345

    def test_heartbeat_details_default_empty(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        data = json.loads((tmp_path / "bridge.hb").read_text())
        assert data["details"] == {}

    def test_heartbeat_creates_directory(self, tmp_path):
        """HeartbeatWriter should create heartbeat_dir if it doesn't exist."""
        nested = tmp_path / "sub" / "dir"
        assert not nested.exists()
        hb = HeartbeatWriter("bridge", str(nested))
        hb.write_heartbeat()
        assert (nested / "bridge.hb").exists()

    def test_heartbeat_overwrites_previous(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat({"frames_total": 1})
        hb.write_heartbeat({"frames_total": 2})
        data = json.loads((tmp_path / "bridge.hb").read_text())
        assert data["details"]["frames_total"] == 2

    def test_no_tmp_file_left_after_write(self, tmp_path):
        """After a successful write, no .tmp files should remain."""
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_interval_stored(self):
        hb = HeartbeatWriter("bridge", "/tmp/test", interval=15.0)
        assert hb.interval == 15.0

    def test_default_interval(self):
        hb = HeartbeatWriter("bridge", "/tmp/test")
        assert hb.interval == 30.0


# ---------------------------------------------------------------------------
# HeartbeatWriter.read_heartbeat
# ---------------------------------------------------------------------------

class TestReadHeartbeat:
    """Tests for the static heartbeat reader."""

    def test_read_existing_heartbeat(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat({"serial_connected": True})
        result = HeartbeatWriter.read_heartbeat("bridge", str(tmp_path))
        assert result is not None
        assert result["details"]["serial_connected"] is True

    def test_read_missing_file_returns_none(self, tmp_path):
        result = HeartbeatWriter.read_heartbeat("nonexistent", str(tmp_path))
        assert result is None

    def test_read_corrupt_file_returns_none(self, tmp_path):
        (tmp_path / "broken.hb").write_text("not valid json {{{")
        result = HeartbeatWriter.read_heartbeat("broken", str(tmp_path))
        assert result is None

    def test_read_empty_file_returns_none(self, tmp_path):
        (tmp_path / "empty.hb").write_text("")
        result = HeartbeatWriter.read_heartbeat("empty", str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# check_service_health
# ---------------------------------------------------------------------------

class TestCheckServiceHealth:
    """Tests for the service health status function."""

    def test_ok_when_fresh(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        assert check_service_health("bridge", str(tmp_path)) == "ok"

    def test_unknown_when_missing(self, tmp_path):
        assert check_service_health("nonexistent", str(tmp_path)) == "unknown"

    def test_stale_when_old(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        hb_file = tmp_path / "bridge.hb"
        # Set mtime to 200 seconds ago
        old_time = time.time() - 200
        os.utime(hb_file, (old_time, old_time))
        assert check_service_health("bridge", str(tmp_path)) == "stale"

    def test_ok_just_under_threshold(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        hb_file = tmp_path / "bridge.hb"
        # Set mtime to 89 seconds ago (just under 90s default threshold)
        old_time = time.time() - 89
        os.utime(hb_file, (old_time, old_time))
        assert check_service_health("bridge", str(tmp_path)) == "ok"

    def test_stale_at_exact_threshold(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        hb_file = tmp_path / "bridge.hb"
        # Set mtime to exactly 90 seconds ago (>= threshold)
        old_time = time.time() - 90
        os.utime(hb_file, (old_time, old_time))
        assert check_service_health("bridge", str(tmp_path)) == "stale"

    def test_custom_threshold(self, tmp_path):
        hb = HeartbeatWriter("bridge", str(tmp_path))
        hb.write_heartbeat()
        hb_file = tmp_path / "bridge.hb"
        # Set mtime to 10 seconds ago
        old_time = time.time() - 10
        os.utime(hb_file, (old_time, old_time))
        # With threshold=5, should be stale
        assert check_service_health("bridge", str(tmp_path), stale_threshold_sec=5) == "stale"
        # With threshold=15, should be ok
        assert check_service_health("bridge", str(tmp_path), stale_threshold_sec=15) == "ok"

    def test_missing_directory_returns_unknown(self):
        assert check_service_health("bridge", "/nonexistent/path/abc123") == "unknown"


# ---------------------------------------------------------------------------
# Phase 2 metrics
# ---------------------------------------------------------------------------


def test_traffic_ingested_counter():
    """traffic_ingested counter is registered and incrementable."""
    from waggle.health import traffic_ingested
    before = traffic_ingested.labels(hive_id="1")._value.get()
    traffic_ingested.labels(hive_id="1").inc()
    after = traffic_ingested.labels(hive_id="1")._value.get()
    assert after == before + 1


def test_traffic_dropped_counter():
    """traffic_dropped counter is registered and incrementable."""
    from waggle.health import traffic_dropped
    before = traffic_dropped.labels(reason="validation")._value.get()
    traffic_dropped.labels(reason="validation").inc()
    after = traffic_dropped.labels(reason="validation")._value.get()
    assert after == before + 1


def test_correlation_alerts_counter():
    """correlation_alerts_fired counter is registered and incrementable."""
    from waggle.health import correlation_alerts_fired
    before = correlation_alerts_fired.labels(type="POSSIBLE_SWARM")._value.get()
    correlation_alerts_fired.labels(type="POSSIBLE_SWARM").inc()
    after = correlation_alerts_fired.labels(type="POSSIBLE_SWARM")._value.get()
    assert after == before + 1


def test_stuck_lanes_gauge():
    """stuck_lanes_current gauge is registered and settable."""
    from waggle.health import stuck_lanes_current
    stuck_lanes_current.labels(hive_id="1").set(2)
    assert stuck_lanes_current.labels(hive_id="1")._value.get() == 2
    stuck_lanes_current.labels(hive_id="1").set(0)
