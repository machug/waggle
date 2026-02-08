"""Pydantic v2 request/response schemas for Waggle API."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


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
    reading_id: int | None
    type: str
    severity: str
    message: str
    acknowledged: bool
    acknowledged_at: str | None
    acknowledged_by: str | None
    created_at: str


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


# --- Error ---


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
