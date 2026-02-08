"""SQLAlchemy ORM models for Waggle."""

from sqlalchemy import (
    REAL,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Hive(Base):
    __tablename__ = "hives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_mac: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    last_seen_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("id BETWEEN 1 AND 250", name="ck_hive_id_range"),
        CheckConstraint(
            "LENGTH(name) BETWEEN 1 AND 64", name="ck_hive_name_length"
        ),
        CheckConstraint(
            "location IS NULL OR LENGTH(location) <= 256",
            name="ck_hive_location_length",
        ),
        CheckConstraint(
            "notes IS NULL OR LENGTH(notes) <= 1024",
            name="ck_hive_notes_length",
        ),
        CheckConstraint(
            "sender_mac IS NULL OR LENGTH(sender_mac) = 17",
            name="ck_hive_mac_format",
        ),
    )


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[str] = mapped_column(Text, nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(REAL, nullable=True)
    temp_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(REAL, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(REAL, nullable=True)
    battery_v: Mapped[float | None] = mapped_column(REAL, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    flags: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sender_mac: Mapped[str] = mapped_column(Text, nullable=False)
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "weight_kg IS NULL OR weight_kg BETWEEN 0 AND 200",
            name="ck_reading_weight",
        ),
        CheckConstraint(
            "temp_c IS NULL OR temp_c BETWEEN -20 AND 60",
            name="ck_reading_temp",
        ),
        CheckConstraint(
            "humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100",
            name="ck_reading_humidity",
        ),
        CheckConstraint(
            "pressure_hpa IS NULL OR pressure_hpa BETWEEN 300 AND 1100",
            name="ck_reading_pressure",
        ),
        CheckConstraint(
            "battery_v IS NULL OR battery_v BETWEEN 2.5 AND 4.5",
            name="ck_reading_battery",
        ),
        CheckConstraint(
            "sequence BETWEEN 0 AND 65535", name="ck_reading_sequence"
        ),
        CheckConstraint(
            "flags BETWEEN 0 AND 255", name="ck_reading_flags"
        ),
        CheckConstraint(
            "LENGTH(sender_mac) = 17", name="ck_reading_mac_format"
        ),
        UniqueConstraint(
            "hive_id", "sequence", "observed_at", name="uq_readings_dedup"
        ),
        Index("idx_readings_hive_time", "hive_id", "observed_at"),
        Index("idx_readings_time", "observed_at"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    acknowledged_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'local'"))
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "type IN ('HIGH_TEMP','LOW_TEMP','HIGH_HUMIDITY','LOW_HUMIDITY',"
            "'RAPID_WEIGHT_LOSS','LOW_BATTERY','NO_DATA','POSSIBLE_SWARM',"
            "'ABSCONDING','ROBBING','LOW_ACTIVITY','VARROA_DETECTED',"
            "'VARROA_HIGH_LOAD','VARROA_RISING','WASP_ATTACK')",
            name="ck_alert_type",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_alert_severity",
        ),
        CheckConstraint(
            "LENGTH(message) BETWEEN 1 AND 256",
            name="ck_alert_message_length",
        ),
        CheckConstraint(
            "acknowledged IN (0, 1)", name="ck_alert_acknowledged"
        ),
        CheckConstraint(
            "acknowledged_by IS NULL OR LENGTH(acknowledged_by) <= 64",
            name="ck_alert_ack_by_length",
        ),
        Index("idx_alerts_hive_type", "hive_id", "type", desc("created_at")),
        Index(
            "idx_alerts_synced",
            "row_synced",
            sqlite_where=text("row_synced = 0"),
        ),
    )


class BeeCount(Base):
    __tablename__ = "bee_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sensor_readings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="(strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
    )
    period_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    bees_in: Mapped[int] = mapped_column(Integer, nullable=False)
    bees_out: Mapped[int] = mapped_column(Integer, nullable=False)
    net_out: Mapped[int] = mapped_column(
        Integer, Computed("bees_out - bees_in")
    )
    total_traffic: Mapped[int] = mapped_column(
        Integer, Computed("bees_in + bees_out")
    )
    lane_mask: Mapped[int] = mapped_column(Integer, nullable=False)
    stuck_mask: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    flags: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sender_mac: Mapped[str] = mapped_column(Text, nullable=False)
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("idx_bee_counts_hive_time", "hive_id", desc("observed_at")),
    )


class CameraNode(Base):
    __tablename__ = "camera_nodes"

    device_id: Mapped[str] = mapped_column(Text, primary_key=True)
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id"), nullable=False
    )
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index(
            "idx_camera_nodes_synced",
            "row_synced",
            sqlite_where=text("row_synced = 0"),
        ),
    )


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        Text, ForeignKey("camera_nodes.device_id"), nullable=False
    )
    boot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at_source: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="(strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    photo_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, server_default="800")
    height: Mapped[int] = mapped_column(Integer, nullable=False, server_default="600")
    ml_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    ml_started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    ml_processed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    ml_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    ml_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    file_synced: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    supabase_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="ck_photo_file_size"),
        CheckConstraint(
            "ml_status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_photo_ml_status",
        ),
        CheckConstraint(
            "captured_at_source IN ('device_ntp', 'device_rtc', 'ingested')",
            name="ck_photo_captured_source",
        ),
        UniqueConstraint(
            "device_id", "boot_id", "sequence", name="uq_photos_device_boot_seq"
        ),
        Index("idx_photos_hive_time", "hive_id", desc("captured_at")),
        Index("idx_photos_ml_status", "ml_status"),
        Index("idx_photos_sha256", "sha256"),
        Index(
            "idx_photos_row_synced",
            "row_synced",
            sqlite_where=text("row_synced = 0"),
        ),
        Index(
            "idx_photos_file_synced",
            "file_synced",
            sqlite_where=text("file_synced = 0"),
        ),
    )


class MlDetection(Base):
    __tablename__ = "ml_detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False
    )
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id", ondelete="RESTRICT"), nullable=False
    )
    detected_at: Mapped[str] = mapped_column(Text, nullable=False)
    top_class: Mapped[str] = mapped_column(Text, nullable=False)
    top_confidence: Mapped[float] = mapped_column(REAL, nullable=False)
    detections_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    varroa_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    pollen_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    wasp_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    bee_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    varroa_max_confidence: Mapped[float] = mapped_column(
        REAL, nullable=False, server_default="0.0"
    )
    inference_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'yolov8n-waggle-v1'")
    )
    model_hash: Mapped[str] = mapped_column(Text, nullable=False)
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "top_class IN ('varroa', 'pollen', 'wasp', 'bee', 'normal')",
            name="ck_detection_class",
        ),
        CheckConstraint(
            "top_confidence BETWEEN 0.0 AND 1.0",
            name="ck_detection_confidence",
        ),
        CheckConstraint(
            "varroa_max_confidence BETWEEN 0.0 AND 1.0",
            name="ck_detection_varroa_conf",
        ),
        CheckConstraint("inference_ms > 0", name="ck_detection_inference_ms"),
        Index("idx_detections_hive_time", "hive_id", desc("detected_at")),
        Index("idx_detections_class", "hive_id", "top_class"),
        Index(
            "idx_detections_synced",
            "row_synced",
            sqlite_where=text("row_synced = 0"),
        ),
    )


class Inspection(Base):
    __tablename__ = "inspections"

    uuid: Mapped[str] = mapped_column(Text, primary_key=True)
    hive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hives.id", ondelete="RESTRICT"), nullable=False
    )
    inspected_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="(strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
    )
    updated_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="(strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
    )
    queen_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    brood_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'local'"))
    row_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("queen_seen IN (0, 1)", name="ck_inspection_queen_seen"),
        CheckConstraint(
            "brood_pattern IN ('good', 'patchy', 'poor') OR brood_pattern IS NULL",
            name="ck_inspection_brood",
        ),
        CheckConstraint(
            "source IN ('local', 'cloud')", name="ck_inspection_source"
        ),
        Index("idx_inspections_hive_time", "hive_id", desc("inspected_at")),
        Index(
            "idx_inspections_synced",
            "row_synced",
            sqlite_where=text("row_synced = 0"),
        ),
    )


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
