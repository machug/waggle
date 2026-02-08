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
    reading_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sensor_readings.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    acknowledged_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "type IN ('POSSIBLE_SWARM','HIGH_TEMP','LOW_TEMP','LOW_BATTERY','NO_DATA')",
            name="ck_alert_type",
        ),
        CheckConstraint(
            "severity IN ('high', 'medium', 'low')",
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
        Index("idx_alerts_hive", "hive_id", "created_at"),
        Index("idx_alerts_unacked", "acknowledged", "created_at"),
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

    __table_args__ = (
        Index("idx_bee_counts_hive_time", "hive_id", desc("observed_at")),
    )
