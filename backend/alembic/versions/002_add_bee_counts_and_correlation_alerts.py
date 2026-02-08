"""add bee_counts table and expand alert types

Revision ID: 002
Revises: 001
Create Date: 2026-02-08

Adds the bee_counts table for Phase 2 bee-counting data with generated columns,
integrity triggers, and append-only protection. Expands the alerts table CHECK
constraints to include Phase 2 alert types and 'high' severity.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Phase 2 alert types (superset of Phase 1)
_ALERT_TYPES_V2 = (
    "'HIGH_TEMP','LOW_TEMP','HIGH_HUMIDITY','LOW_HUMIDITY',"
    "'RAPID_WEIGHT_LOSS','LOW_BATTERY','NO_DATA',"
    "'POSSIBLE_SWARM','ABSCONDING','ROBBING','LOW_ACTIVITY'"
)

# Phase 1 alert types (for downgrade)
_ALERT_TYPES_V1 = "'POSSIBLE_SWARM','HIGH_TEMP','LOW_TEMP','LOW_BATTERY','NO_DATA'"


def upgrade() -> None:
    # --- bee_counts table ---
    op.execute("""
        CREATE TABLE bee_counts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            reading_id      INTEGER NOT NULL UNIQUE
                                REFERENCES sensor_readings(id) ON DELETE CASCADE,
            hive_id         INTEGER NOT NULL
                                REFERENCES hives(id) ON DELETE RESTRICT,
            observed_at     TEXT NOT NULL
                                CHECK(LENGTH(observed_at) = 24
                                      AND observed_at GLOB '????-??-??T??:??:??.???Z'),
            ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                                CHECK(LENGTH(ingested_at) = 24),
            period_ms       INTEGER NOT NULL CHECK(period_ms BETWEEN 1000 AND 65535),
            bees_in         INTEGER NOT NULL CHECK(bees_in BETWEEN 0 AND 65535),
            bees_out        INTEGER NOT NULL CHECK(bees_out BETWEEN 0 AND 65535),
            net_out         INTEGER GENERATED ALWAYS AS (bees_out - bees_in) STORED,
            total_traffic   INTEGER GENERATED ALWAYS AS (bees_in + bees_out) STORED,
            lane_mask       INTEGER NOT NULL CHECK(lane_mask BETWEEN 0 AND 255),
            stuck_mask      INTEGER NOT NULL CHECK(stuck_mask BETWEEN 0 AND 255),
            sequence        INTEGER NOT NULL CHECK(sequence BETWEEN 0 AND 65535),
            flags           INTEGER NOT NULL DEFAULT 0 CHECK(flags BETWEEN 0 AND 255),
            sender_mac      TEXT NOT NULL CHECK(LENGTH(sender_mac) = 17)
        );
    """)

    op.execute(
        "CREATE INDEX idx_bee_counts_hive_time ON bee_counts(hive_id, observed_at DESC);"
    )

    # --- integrity trigger: validate bee_counts against sensor_readings ---
    op.execute("""
        CREATE TRIGGER bee_counts_validate_insert
        BEFORE INSERT ON bee_counts
        BEGIN
            SELECT CASE
                WHEN (SELECT hive_id FROM sensor_readings
                      WHERE id = NEW.reading_id) IS NULL
                    THEN RAISE(ABORT, 'reading_id not found in sensor_readings')
                WHEN (SELECT hive_id FROM sensor_readings
                      WHERE id = NEW.reading_id) != NEW.hive_id
                    THEN RAISE(ABORT, 'hive_id mismatch with sensor_readings')
                WHEN (SELECT observed_at FROM sensor_readings
                      WHERE id = NEW.reading_id) != NEW.observed_at
                    THEN RAISE(ABORT, 'observed_at mismatch with sensor_readings')
                WHEN (SELECT sequence FROM sensor_readings
                      WHERE id = NEW.reading_id) != NEW.sequence
                    THEN RAISE(ABORT, 'sequence mismatch with sensor_readings')
                WHEN (SELECT flags FROM sensor_readings
                      WHERE id = NEW.reading_id) != NEW.flags
                    THEN RAISE(ABORT, 'flags mismatch with sensor_readings')
                WHEN (SELECT sender_mac FROM sensor_readings
                      WHERE id = NEW.reading_id) != NEW.sender_mac
                    THEN RAISE(ABORT, 'sender_mac mismatch with sensor_readings')
            END;
        END;
    """)

    # --- append-only trigger ---
    op.execute("""
        CREATE TRIGGER bee_counts_no_update
        BEFORE UPDATE ON bee_counts
        BEGIN
            SELECT RAISE(ABORT, 'bee_counts is append-only; updates are not permitted');
        END;
    """)

    # --- expand alerts CHECK constraints (SQLite requires table recreation) ---
    op.execute("ALTER TABLE alerts RENAME TO _alerts_old;")

    op.execute(f"""
        CREATE TABLE alerts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id          INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            reading_id       INTEGER REFERENCES sensor_readings(id) ON DELETE SET NULL,
            type             TEXT NOT NULL
                                CHECK(type IN ({_ALERT_TYPES_V2})),
            severity         TEXT NOT NULL
                                CHECK(severity IN ('critical','high','medium','low')),
            message          TEXT NOT NULL
                                CHECK(LENGTH(message) BETWEEN 1 AND 256),
            acknowledged     INTEGER NOT NULL DEFAULT 0
                                CHECK(acknowledged IN (0, 1)),
            acknowledged_at  TEXT,
            acknowledged_by  TEXT
                                CHECK(acknowledged_by IS NULL
                                      OR LENGTH(acknowledged_by) <= 64),
            created_at       TEXT NOT NULL
        );
    """)

    op.execute("INSERT INTO alerts SELECT * FROM _alerts_old;")
    op.execute("DROP TABLE _alerts_old;")

    op.execute("CREATE INDEX idx_alerts_hive ON alerts(hive_id, created_at);")
    op.execute("CREATE INDEX idx_alerts_unacked ON alerts(acknowledged, created_at);")


def downgrade() -> None:
    # --- drop bee_counts (triggers are dropped automatically with the table) ---
    op.execute("DROP TABLE IF EXISTS bee_counts;")

    # --- restore alerts with Phase 1-only CHECK constraints ---
    op.execute("ALTER TABLE alerts RENAME TO _alerts_old;")

    op.execute(f"""
        CREATE TABLE alerts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id          INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            reading_id       INTEGER REFERENCES sensor_readings(id) ON DELETE SET NULL,
            type             TEXT NOT NULL
                                CHECK(type IN ({_ALERT_TYPES_V1})),
            severity         TEXT NOT NULL
                                CHECK(severity IN ('high','medium','low')),
            message          TEXT NOT NULL
                                CHECK(LENGTH(message) BETWEEN 1 AND 256),
            acknowledged     INTEGER NOT NULL DEFAULT 0
                                CHECK(acknowledged IN (0, 1)),
            acknowledged_at  TEXT,
            acknowledged_by  TEXT
                                CHECK(acknowledged_by IS NULL
                                      OR LENGTH(acknowledged_by) <= 64),
            created_at       TEXT NOT NULL
        );
    """)

    op.execute("INSERT INTO alerts SELECT * FROM _alerts_old;")
    op.execute("DROP TABLE _alerts_old;")

    op.execute("CREATE INDEX idx_alerts_hive ON alerts(hive_id, created_at);")
    op.execute("CREATE INDEX idx_alerts_unacked ON alerts(acknowledged, created_at);")
