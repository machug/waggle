"""Prometheus metrics definitions and heartbeat health-check utilities.

Metrics are defined as module-level singletons so that any module can
import and increment them.  The HeartbeatWriter provides atomic file
writes for liveness checks.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Prometheus metrics  (module-level singletons)
# ---------------------------------------------------------------------------

# --- API metrics (exposed via prometheus-fastapi-instrumentator at :9100) ---
api_request_duration = Histogram(
    "waggle_api_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path", "status"],
)

# --- Bridge metrics (exposed via prometheus_client at :9101) ---
bridge_frames_received = Counter(
    "waggle_bridge_frames_received_total",
    "Total serial frames received by the bridge",
)
bridge_crc_failures = Counter(
    "waggle_bridge_crc_failures_total",
    "Total CRC check failures in received frames",
)
mqtt_publish_failures = Counter(
    "waggle_mqtt_publish_failures_total",
    "Total MQTT publish failures",
)
serial_reconnects = Counter(
    "waggle_serial_reconnects_total",
    "Total serial port reconnect attempts",
)

# --- Worker metrics (exposed via prometheus_client at :9102) ---
readings_ingested = Counter(
    "waggle_readings_ingested_total",
    "Total sensor readings successfully ingested",
    labelnames=["hive_id"],
)
readings_dropped = Counter(
    "waggle_readings_dropped_total",
    "Total sensor readings dropped",
    labelnames=["hive_id", "reason"],
)
alerts_fired = Counter(
    "waggle_alerts_fired_total",
    "Total alerts fired",
    labelnames=["hive_id", "type"],
)

# --- Phase 2 Traffic metrics ---
traffic_ingested = Counter(
    "waggle_traffic_ingested_total",
    "Total bee count records successfully ingested",
    labelnames=["hive_id"],
)
traffic_dropped = Counter(
    "waggle_traffic_dropped_total",
    "Total bee count records dropped",
    labelnames=["reason"],
)
correlation_alerts_fired = Counter(
    "waggle_alerts_correlation_total",
    "Total correlation alerts fired",
    labelnames=["type"],
)
stuck_lanes_current = Gauge(
    "waggle_stuck_lanes_current",
    "Current number of stuck lanes per hive",
    labelnames=["hive_id"],
)

# ---------------------------------------------------------------------------
# Heartbeat writer / reader
# ---------------------------------------------------------------------------

class HeartbeatWriter:
    """Writes periodic heartbeat files with atomic rename.

    Usage::

        hb = HeartbeatWriter("bridge", "/var/lib/waggle/health")
        # In your main loop every ~30s:
        hb.write_heartbeat({"serial_connected": True, "frames_total": 123})
    """

    def __init__(
        self,
        service_name: str,
        heartbeat_dir: str,
        interval: float = 30.0,
    ) -> None:
        self.service_name = service_name
        self.heartbeat_dir = Path(heartbeat_dir)
        self.interval = interval
        self._start_monotonic = time.monotonic()

    # -- write ---------------------------------------------------------------

    def write_heartbeat(self, details: dict | None = None) -> None:
        """Write a heartbeat JSON file atomically.

        Writes to ``<service>.hb.tmp`` then renames to ``<service>.hb`` so
        readers never see partial content.
        """
        self.heartbeat_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC)
        payload = {
            "pid": os.getpid(),
            "uptime_sec": round(time.monotonic() - self._start_monotonic, 1),
            "ts": now.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{now.microsecond // 1000:03d}Z",
            "details": details or {},
        }

        final_path = self.heartbeat_dir / f"{self.service_name}.hb"
        # Use a temp file in the same directory so os.rename is atomic
        # (same filesystem).
        fd, tmp_path = tempfile.mkstemp(
            dir=self.heartbeat_dir,
            prefix=f"{self.service_name}.hb.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
            os.rename(tmp_path, final_path)
        except BaseException:
            # Clean up temp file on any error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # -- read (static) -------------------------------------------------------

    @staticmethod
    def read_heartbeat(service_name: str, heartbeat_dir: str) -> dict | None:
        """Read and parse a heartbeat file, returning None on any failure."""
        hb_path = Path(heartbeat_dir) / f"{service_name}.hb"
        try:
            with open(hb_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Service health check
# ---------------------------------------------------------------------------

def check_service_health(
    service_name: str,
    heartbeat_dir: str,
    stale_threshold_sec: int = 90,
) -> str:
    """Check a service's health based on its heartbeat file mtime.

    Returns:
        ``"ok"`` if the file exists and was modified within *stale_threshold_sec*,
        ``"stale"`` if the file exists but is older than *stale_threshold_sec*,
        ``"unknown"`` if the file is missing.
    """
    hb_path = Path(heartbeat_dir) / f"{service_name}.hb"
    try:
        mtime = hb_path.stat().st_mtime
    except OSError:
        return "unknown"

    age = time.time() - mtime
    if age < stale_threshold_sec:
        return "ok"
    return "stale"
