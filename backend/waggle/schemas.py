"""Pydantic v2 request/response schemas for Waggle API."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")

CanonicalTimestamp = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$",
        min_length=24,
        max_length=24,
    ),
]


# --- Hives ---


class HiveCreate(BaseModel):
    id: int = Field(ge=1, le=250)
    name: str = Field(min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=1024)
    sender_mac: str | None = None

    @field_validator("sender_mac", mode="before")
    @classmethod
    def normalize_mac(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not MAC_RE.match(v):
            raise ValueError("sender_mac must match AA:BB:CC:DD:EE:FF format")
        return v.upper()


class HiveUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=1024)
    sender_mac: str | None = None

    @field_validator("sender_mac", mode="before")
    @classmethod
    def normalize_mac(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not MAC_RE.match(v):
            raise ValueError("sender_mac must match AA:BB:CC:DD:EE:FF format")
        return v.upper()


class LatestReading(BaseModel):
    weight_kg: float | None
    temp_c: float | None
    humidity_pct: float | None
    pressure_hpa: float | None
    battery_v: float | None
    observed_at: str
    flags: int


class LatestTrafficOut(BaseModel):
    """Latest traffic embedded in hive detail."""

    observed_at: str
    bees_in: int
    bees_out: int
    net_out: int
    total_traffic: int


class HiveOut(BaseModel):
    id: int
    name: str
    location: str | None
    notes: str | None
    sender_mac: str | None
    last_seen_at: str | None
    created_at: str
    latest_reading: LatestReading | None = None
    latest_traffic: LatestTrafficOut | None = None
    activity_score_today: int | None = None
    camera_node_id: str | None = None
    latest_photo_at: str | None = None
    latest_ml_status: str | None = None
    varroa_ratio: float | None = None


class HivesResponse(BaseModel):
    items: list[HiveOut]
    total: int
    limit: int
    offset: int


# --- Readings ---


class ReadingOut(BaseModel):
    id: int
    hive_id: int
    observed_at: str
    weight_kg: float | None
    temp_c: float | None
    humidity_pct: float | None
    pressure_hpa: float | None
    battery_v: float | None
    sequence: int
    flags: int


class AggregatedReading(BaseModel):
    period_start: str
    period_end: str
    count: int
    avg_weight_kg: float | None
    min_weight_kg: float | None
    max_weight_kg: float | None
    avg_temp_c: float | None
    min_temp_c: float | None
    max_temp_c: float | None
    avg_humidity_pct: float | None
    min_humidity_pct: float | None
    max_humidity_pct: float | None
    avg_pressure_hpa: float | None
    min_pressure_hpa: float | None
    max_pressure_hpa: float | None
    avg_battery_v: float | None
    min_battery_v: float | None
    max_battery_v: float | None


class ReadingsResponse(BaseModel):
    items: list[ReadingOut] | list[AggregatedReading]
    interval: Literal["raw", "hourly", "daily"]
    total: int
    limit: int
    offset: int


# --- Traffic ---


class TrafficRecordOut(BaseModel):
    """Single bee count record (raw interval)."""

    id: int
    reading_id: int
    hive_id: int
    observed_at: str
    period_ms: int
    bees_in: int
    bees_out: int
    net_out: int
    total_traffic: int
    lane_mask: int
    stuck_mask: int
    flags: int


class TrafficAggregateOut(BaseModel):
    """Aggregated traffic for hourly/daily interval."""

    period_start: str
    period_end: str
    reading_count: int
    sum_bees_in: int
    sum_bees_out: int
    sum_net_out: int
    sum_total_traffic: int
    avg_bees_in_per_min: float
    avg_bees_out_per_min: float


class TrafficResponse(BaseModel):
    """Paginated traffic response."""

    items: list[TrafficRecordOut | TrafficAggregateOut]
    interval: str  # "raw", "hourly", "daily"
    total: int
    limit: int
    offset: int


class TrafficSummaryOut(BaseModel):
    """Daily traffic summary."""

    date: str
    total_in: int
    total_out: int
    net_out: int
    total_traffic: int
    peak_hour: int | None
    rolling_7d_avg_total: int | None
    activity_score: int | None


# --- Alerts ---


class AlertOut(BaseModel):
    id: int
    hive_id: int
    type: str
    severity: str
    message: str
    observed_at: str
    acknowledged: bool
    acknowledged_at: str | None
    acknowledged_by: str | None
    created_at: str
    notified_at: str | None = None
    updated_at: str | None = None
    source: str = "local"
    details_json: str | None = None


class AlertsResponse(BaseModel):
    items: list[AlertOut]
    total: int
    limit: int
    offset: int


class AlertAcknowledge(BaseModel):
    acknowledged_by: str | None = Field(default=None, max_length=64)


# --- Hub Status ---


class ServiceHealth(BaseModel):
    bridge: str
    worker: str
    mqtt: str
    api: str


class HubStatusOut(BaseModel):
    status: str
    uptime_sec: int
    last_ingest_at: str | None
    mqtt_connected: bool
    disk_free_mb: int
    hive_count: int
    reading_count_24h: int
    services: ServiceHealth
    traffic_readings_24h: int = 0
    phase2_nodes_active: int = 0
    stuck_lanes_total: int = 0
    photos_24h: int = 0
    ml_queue_depth: int = 0
    detections_24h: int = 0
    sync_pending_rows: int = 0
    sync_pending_files: int = 0


# --- Camera Nodes ---


class CameraNodeCreate(BaseModel):
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")
    hive_id: int = Field(ge=1, le=250)
    api_key: str = Field(min_length=32)


class CameraNodeOut(BaseModel):
    device_id: str
    hive_id: int
    created_at: str
    last_seen_at: str | None = None


# --- Photos ---


class PhotoOutLocal(BaseModel):
    """Photo response for Pi local API (local-mode dashboard)."""

    id: int
    hive_id: int
    device_id: str
    boot_id: int
    captured_at: str
    captured_at_source: Literal["device_ntp", "device_rtc", "ingested"]
    sequence: int
    local_image_url: str
    local_image_expires_at: int
    file_size_bytes: int
    sha256: str
    ml_status: Literal["pending", "processing", "completed", "failed"]
    ml_processed_at: str | None = None
    ml_attempts: int
    ml_error: str | None = None


class PhotoRowCloud(BaseModel):
    """Photo data as stored in Supabase for cloud dashboard."""

    id: int
    hive_id: int
    device_id: str
    boot_id: int
    captured_at: str
    captured_at_source: Literal["device_ntp", "device_rtc", "ingested"]
    sequence: int
    supabase_path: str | None = None
    file_size_bytes: int
    sha256: str
    ml_status: Literal["pending", "processing", "completed", "failed"]
    ml_processed_at: str | None = None
    ml_attempts: int
    ml_error: str | None = None


class PhotosResponse(BaseModel):
    items: list[PhotoOutLocal]
    total: int
    limit: int
    offset: int


# --- Detections ---


class DetectionOut(BaseModel):
    id: int
    photo_id: int
    hive_id: int
    detected_at: str
    top_class: Literal["varroa", "pollen", "wasp", "bee", "normal"]
    top_confidence: float
    detections_json: list[dict]
    varroa_count: int
    pollen_count: int
    wasp_count: int
    bee_count: int
    inference_ms: int
    model_version: str
    model_hash: str


class DetectionsResponse(BaseModel):
    items: list[DetectionOut]
    total: int
    limit: int
    offset: int


class VarroaDailyOut(BaseModel):
    date: str  # YYYY-MM-DD
    total_mites: int
    total_bees: int
    mites_per_100_bees: float | None
    photo_count: int


class VarroaSummaryOut(BaseModel):
    hive_id: int
    hive_name: str | None = None
    current_ratio: float | None
    trend_7d: Literal["rising", "falling", "stable", "insufficient_data"]
    trend_slope: float | None
    days_since_treatment: int | None
    treatment_threshold: float = 3.0


# --- Inspections ---


class InspectionIn(BaseModel):
    uuid: str | None = None
    hive_id: int = Field(ge=1, le=250)
    inspected_at: str = Field(min_length=24, max_length=24)
    queen_seen: bool = False
    brood_pattern: Literal["good", "patchy", "poor"] | None = None
    treatment_type: str | None = None
    treatment_notes: str | None = None
    notes: str | None = None


class InspectionUpdate(BaseModel):
    hive_id: int = Field(ge=1, le=250)
    inspected_at: str = Field(min_length=24, max_length=24)
    queen_seen: bool = False
    brood_pattern: Literal["good", "patchy", "poor"] | None = None
    treatment_type: str | None = None
    treatment_notes: str | None = None
    notes: str | None = None


class InspectionOut(BaseModel):
    uuid: str
    hive_id: int
    inspected_at: str
    updated_at: str | None = None
    queen_seen: bool
    brood_pattern: Literal["good", "patchy", "poor"] | None
    treatment_type: str | None
    treatment_notes: str | None
    notes: str | None
    source: Literal["local", "cloud"]


class InspectionsResponse(BaseModel):
    items: list[InspectionOut]
    total: int
    limit: int
    offset: int


# --- Webhooks ---


class WebhookPayload(BaseModel):
    alert_id: int
    type: str
    severity: Literal["critical", "high", "medium", "low"]
    hive_id: int
    hive_name: str | None
    message: str
    observed_at: str
    created_at: str
    details: dict | None = None


# --- Sync ---


class SyncStatusOut(BaseModel):
    last_push_at: str | None = None
    last_pull_inspections_at: str | None = None
    last_pull_alerts_at: str | None = None
    pending_rows: int
    pending_files: int


# --- Weather ---


class WeatherOut(BaseModel):
    provider: str
    temp_c: float | None = None
    humidity_pct: float | None = None
    description: str | None = None
    icon: str | None = None
    wind_speed_ms: float | None = None
    fetched_at: str | None = None


# --- Error ---


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
