"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-08

Creates the hives, sensor_readings, and alerts tables with all CHECK constraints,
unique constraints, indexes, and foreign keys matching waggle/models.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- hives ---
    op.create_table(
        "hives",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("sender_mac", sa.Text, nullable=True),
        sa.Column("last_seen_at", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("id BETWEEN 1 AND 250", name="ck_hive_id_range"),
        sa.CheckConstraint("LENGTH(name) BETWEEN 1 AND 64", name="ck_hive_name_length"),
        sa.CheckConstraint(
            "location IS NULL OR LENGTH(location) <= 256",
            name="ck_hive_location_length",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR LENGTH(notes) <= 1024",
            name="ck_hive_notes_length",
        ),
        sa.CheckConstraint(
            "sender_mac IS NULL OR LENGTH(sender_mac) = 17",
            name="ck_hive_mac_format",
        ),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("sender_mac"),
    )

    # --- sensor_readings ---
    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "hive_id",
            sa.Integer,
            sa.ForeignKey("hives.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.Text, nullable=False),
        sa.Column("ingested_at", sa.Text, nullable=False),
        sa.Column("weight_kg", sa.REAL, nullable=True),
        sa.Column("temp_c", sa.REAL, nullable=True),
        sa.Column("humidity_pct", sa.REAL, nullable=True),
        sa.Column("pressure_hpa", sa.REAL, nullable=True),
        sa.Column("battery_v", sa.REAL, nullable=True),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("flags", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sender_mac", sa.Text, nullable=False),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg BETWEEN 0 AND 200",
            name="ck_reading_weight",
        ),
        sa.CheckConstraint(
            "temp_c IS NULL OR temp_c BETWEEN -20 AND 60",
            name="ck_reading_temp",
        ),
        sa.CheckConstraint(
            "humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100",
            name="ck_reading_humidity",
        ),
        sa.CheckConstraint(
            "pressure_hpa IS NULL OR pressure_hpa BETWEEN 300 AND 1100",
            name="ck_reading_pressure",
        ),
        sa.CheckConstraint(
            "battery_v IS NULL OR battery_v BETWEEN 2.5 AND 4.5",
            name="ck_reading_battery",
        ),
        sa.CheckConstraint("sequence BETWEEN 0 AND 65535", name="ck_reading_sequence"),
        sa.CheckConstraint("flags BETWEEN 0 AND 255", name="ck_reading_flags"),
        sa.CheckConstraint("LENGTH(sender_mac) = 17", name="ck_reading_mac_format"),
        sa.UniqueConstraint("hive_id", "sequence", "observed_at", name="uq_readings_dedup"),
    )

    op.create_index("idx_readings_hive_time", "sensor_readings", ["hive_id", "observed_at"])
    op.create_index("idx_readings_time", "sensor_readings", ["observed_at"])

    # --- alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "hive_id",
            sa.Integer,
            sa.ForeignKey("hives.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reading_id",
            sa.Integer,
            sa.ForeignKey("sensor_readings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("acknowledged", sa.Integer, nullable=False, server_default="0"),
        sa.Column("acknowledged_at", sa.Text, nullable=True),
        sa.Column("acknowledged_by", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "type IN ('POSSIBLE_SWARM','HIGH_TEMP','LOW_TEMP','LOW_BATTERY','NO_DATA')",
            name="ck_alert_type",
        ),
        sa.CheckConstraint(
            "severity IN ('high', 'medium', 'low')",
            name="ck_alert_severity",
        ),
        sa.CheckConstraint(
            "LENGTH(message) BETWEEN 1 AND 256",
            name="ck_alert_message_length",
        ),
        sa.CheckConstraint("acknowledged IN (0, 1)", name="ck_alert_acknowledged"),
        sa.CheckConstraint(
            "acknowledged_by IS NULL OR LENGTH(acknowledged_by) <= 64",
            name="ck_alert_ack_by_length",
        ),
    )

    op.create_index("idx_alerts_hive", "alerts", ["hive_id", "created_at"])
    op.create_index("idx_alerts_unacked", "alerts", ["acknowledged", "created_at"])


def downgrade() -> None:
    # Drop in reverse order respecting foreign key dependencies
    op.drop_table("alerts")
    op.drop_table("sensor_readings")
    op.drop_table("hives")
