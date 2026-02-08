"""add vision, cloud sync, and webhook tables

Revision ID: 003
Revises: 002
Create Date: 2026-02-08

Creates camera_nodes, photos, ml_detections, inspections, sync_state tables.
Recreates alerts with expanded types + sync columns.
Adds row_synced to hives, sensor_readings, bee_counts.
Creates 8 row_synced reset triggers.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0a. Add row_synced to hives
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE hives ADD COLUMN row_synced INTEGER NOT NULL DEFAULT 0"
        " CHECK(row_synced IN (0, 1));"
    )
    op.execute(
        "CREATE INDEX idx_hives_synced ON hives(row_synced) WHERE row_synced = 0;"
    )

    # ------------------------------------------------------------------
    # 0b. Create camera_nodes table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE camera_nodes (
            device_id    TEXT PRIMARY KEY,
            hive_id      INTEGER NOT NULL REFERENCES hives(id),
            api_key_hash TEXT NOT NULL,
            created_at   TEXT NOT NULL CHECK(LENGTH(created_at) = 24),
            last_seen_at TEXT CHECK(last_seen_at IS NULL OR LENGTH(last_seen_at) = 24),
            row_synced   INTEGER NOT NULL DEFAULT 0 CHECK(row_synced IN (0, 1))
        );
    """)
    op.execute(
        "CREATE INDEX idx_camera_nodes_synced ON camera_nodes(row_synced)"
        " WHERE row_synced = 0;"
    )

    # ------------------------------------------------------------------
    # 1. Create photos table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE photos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id             INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            device_id           TEXT NOT NULL REFERENCES camera_nodes(device_id),
            boot_id             INTEGER NOT NULL,
            captured_at         TEXT NOT NULL
                                    CHECK(LENGTH(captured_at) = 24
                                          AND captured_at GLOB '????-??-??T??:??:??.???Z'),
            captured_at_source  TEXT NOT NULL
                                    CHECK(captured_at_source IN
                                          ('device_ntp', 'device_rtc', 'ingested')),
            ingested_at         TEXT NOT NULL
                                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                                    CHECK(LENGTH(ingested_at) = 24),
            sequence            INTEGER NOT NULL,
            photo_path          TEXT NOT NULL,
            file_size_bytes     INTEGER NOT NULL CHECK(file_size_bytes > 0),
            sha256              TEXT NOT NULL,
            width               INTEGER NOT NULL DEFAULT 800,
            height              INTEGER NOT NULL DEFAULT 600,
            ml_status           TEXT NOT NULL DEFAULT 'pending'
                                    CHECK(ml_status IN
                                          ('pending', 'processing', 'completed', 'failed')),
            ml_started_at       TEXT CHECK(ml_started_at IS NULL
                                          OR LENGTH(ml_started_at) = 24),
            ml_processed_at     TEXT CHECK(ml_processed_at IS NULL
                                          OR LENGTH(ml_processed_at) = 24),
            ml_attempts         INTEGER NOT NULL DEFAULT 0,
            ml_error            TEXT,
            row_synced          INTEGER NOT NULL DEFAULT 0 CHECK(row_synced IN (0, 1)),
            file_synced         INTEGER NOT NULL DEFAULT 0 CHECK(file_synced IN (0, 1)),
            supabase_path       TEXT
        );
    """)
    op.execute(
        "CREATE INDEX idx_photos_hive_time ON photos(hive_id, captured_at DESC);"
    )
    op.execute(
        "CREATE INDEX idx_photos_ml_status ON photos(ml_status)"
        " WHERE ml_status IN ('pending', 'processing');"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_photos_device_boot_seq"
        " ON photos(device_id, boot_id, sequence);"
    )
    op.execute(
        "CREATE INDEX idx_photos_row_synced ON photos(row_synced) WHERE row_synced = 0;"
    )
    op.execute(
        "CREATE INDEX idx_photos_file_synced ON photos(file_synced) WHERE file_synced = 0;"
    )
    op.execute("CREATE INDEX idx_photos_sha256 ON photos(sha256);")

    # ------------------------------------------------------------------
    # 2. Create ml_detections table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE ml_detections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id        INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
            hive_id         INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            detected_at     TEXT NOT NULL
                                CHECK(LENGTH(detected_at) = 24
                                      AND detected_at GLOB '????-??-??T??:??:??.???Z'),
            top_class       TEXT NOT NULL
                                CHECK(top_class IN
                                      ('varroa', 'pollen', 'wasp', 'bee', 'normal')),
            top_confidence  REAL NOT NULL CHECK(top_confidence BETWEEN 0.0 AND 1.0),
            detections_json TEXT NOT NULL DEFAULT '[]',
            varroa_count    INTEGER NOT NULL DEFAULT 0 CHECK(varroa_count >= 0),
            pollen_count    INTEGER NOT NULL DEFAULT 0 CHECK(pollen_count >= 0),
            wasp_count      INTEGER NOT NULL DEFAULT 0 CHECK(wasp_count >= 0),
            bee_count       INTEGER NOT NULL DEFAULT 0 CHECK(bee_count >= 0),
            varroa_max_confidence REAL NOT NULL DEFAULT 0.0
                                CHECK(varroa_max_confidence BETWEEN 0.0 AND 1.0),
            inference_ms    INTEGER NOT NULL CHECK(inference_ms > 0),
            model_version   TEXT NOT NULL DEFAULT 'yolov8n-waggle-v1',
            model_hash      TEXT NOT NULL,
            row_synced      INTEGER NOT NULL DEFAULT 0 CHECK(row_synced IN (0, 1))
        );
    """)
    op.execute(
        "CREATE INDEX idx_detections_hive_time"
        " ON ml_detections(hive_id, detected_at DESC);"
    )
    op.execute(
        "CREATE INDEX idx_detections_class ON ml_detections(hive_id, top_class);"
    )
    op.execute(
        "CREATE INDEX idx_detections_synced ON ml_detections(row_synced)"
        " WHERE row_synced = 0;"
    )

    # ------------------------------------------------------------------
    # 3. Create inspections table (UUID PK)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE inspections (
            uuid            TEXT PRIMARY KEY,
            hive_id         INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            inspected_at    TEXT NOT NULL
                                CHECK(LENGTH(inspected_at) = 24
                                      AND inspected_at GLOB '????-??-??T??:??:??.???Z'),
            created_at      TEXT NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                                CHECK(LENGTH(created_at) = 24),
            updated_at      TEXT NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                                CHECK(LENGTH(updated_at) = 24),
            queen_seen      INTEGER NOT NULL DEFAULT 0 CHECK(queen_seen IN (0, 1)),
            brood_pattern   TEXT CHECK(brood_pattern IN ('good', 'patchy', 'poor')
                                       OR brood_pattern IS NULL),
            treatment_type  TEXT,
            treatment_notes TEXT,
            notes           TEXT,
            source          TEXT NOT NULL DEFAULT 'local'
                                CHECK(source IN ('local', 'cloud')),
            row_synced      INTEGER NOT NULL DEFAULT 0 CHECK(row_synced IN (0, 1))
        );
    """)
    op.execute(
        "CREATE INDEX idx_inspections_hive_time"
        " ON inspections(hive_id, inspected_at DESC);"
    )
    op.execute(
        "CREATE INDEX idx_inspections_synced ON inspections(row_synced)"
        " WHERE row_synced = 0;"
    )

    # ------------------------------------------------------------------
    # 3b. Create sync_state table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE sync_state (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # ------------------------------------------------------------------
    # 4. Add row_synced to existing tables
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE sensor_readings ADD COLUMN row_synced INTEGER NOT NULL DEFAULT 0"
        " CHECK(row_synced IN (0, 1));"
    )
    op.execute(
        "ALTER TABLE bee_counts ADD COLUMN row_synced INTEGER NOT NULL DEFAULT 0"
        " CHECK(row_synced IN (0, 1));"
    )
    op.execute(
        "CREATE INDEX idx_sensor_readings_synced ON sensor_readings(row_synced)"
        " WHERE row_synced = 0;"
    )
    op.execute(
        "CREATE INDEX idx_bee_counts_synced ON bee_counts(row_synced)"
        " WHERE row_synced = 0;"
    )

    # ------------------------------------------------------------------
    # 5. Recreate alerts table with expanded types + sync columns
    #    SQLite can't ALTER CHECK constraints, so we must recreate.
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE alerts RENAME TO _alerts_old;")

    op.execute("""
        CREATE TABLE alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id         INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            type            TEXT NOT NULL CHECK(type IN (
                'HIGH_TEMP','LOW_TEMP','HIGH_HUMIDITY','LOW_HUMIDITY',
                'RAPID_WEIGHT_LOSS','LOW_BATTERY','NO_DATA',
                'POSSIBLE_SWARM','ABSCONDING','ROBBING','LOW_ACTIVITY',
                'VARROA_DETECTED','VARROA_HIGH_LOAD','VARROA_RISING','WASP_ATTACK'
            )),
            severity        TEXT NOT NULL DEFAULT 'medium' CHECK(severity IN (
                'critical','high','medium','low'
            )),
            message         TEXT NOT NULL,
            observed_at     TEXT NOT NULL CHECK(LENGTH(observed_at) = 24),
            created_at      TEXT NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                                CHECK(LENGTH(created_at) = 24),
            acknowledged    INTEGER NOT NULL DEFAULT 0 CHECK(acknowledged IN (0,1)),
            acknowledged_at TEXT CHECK(acknowledged_at IS NULL
                                      OR LENGTH(acknowledged_at) = 24),
            acknowledged_by TEXT,
            details_json    TEXT,
            notified_at     TEXT CHECK(notified_at IS NULL
                                      OR LENGTH(notified_at) = 24),
            row_synced      INTEGER NOT NULL DEFAULT 0 CHECK(row_synced IN (0, 1)),
            updated_at      TEXT NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                                CHECK(LENGTH(updated_at) = 24),
            source          TEXT NOT NULL DEFAULT 'local'
                                CHECK(source IN ('local', 'cloud'))
        );
    """)

    # Migrate data from old alerts.
    # v002 alerts do not have observed_at or details columns, so we use
    # created_at as fallback for observed_at and NULL for details_json.
    # CRITICAL: notified_at = created_at to prevent webhook storm on
    # historical alerts.
    op.execute("""
        INSERT INTO alerts (id, hive_id, type, severity, message, observed_at,
                            created_at, acknowledged, acknowledged_at, acknowledged_by,
                            details_json, notified_at, row_synced, updated_at, source)
        SELECT id, hive_id, type, severity, message, created_at,
               created_at, acknowledged, acknowledged_at, acknowledged_by,
               NULL, created_at, 0, created_at, 'local'
        FROM _alerts_old;
    """)

    op.execute("DROP TABLE _alerts_old;")
    op.execute(
        "CREATE INDEX idx_alerts_hive_type ON alerts(hive_id, type, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX idx_alerts_synced ON alerts(row_synced) WHERE row_synced = 0;"
    )

    # ------------------------------------------------------------------
    # 6. Create 8 row_synced reset triggers
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TRIGGER hives_row_synced_reset
        AFTER UPDATE OF name, location ON hives
        WHEN NEW.row_synced = 1
        BEGIN
            UPDATE hives SET row_synced = 0 WHERE id = NEW.id;
        END;
    """)

    op.execute("""
        CREATE TRIGGER sensor_readings_row_synced_reset
        AFTER UPDATE OF temp_c, humidity_pct, weight_kg, battery_v,
                        pressure_hpa, observed_at ON sensor_readings
        WHEN NEW.row_synced = 1
        BEGIN
            UPDATE sensor_readings SET row_synced = 0 WHERE id = NEW.id;
        END;
    """)

    op.execute("""
        CREATE TRIGGER bee_counts_row_synced_reset
        AFTER UPDATE OF bees_in, bees_out, period_ms, lane_mask,
                        stuck_mask ON bee_counts
        WHEN NEW.row_synced = 1
        BEGIN
            UPDATE bee_counts SET row_synced = 0 WHERE id = NEW.id;
        END;
    """)

    op.execute("""
        CREATE TRIGGER photos_row_synced_reset
        AFTER UPDATE OF captured_at, captured_at_source, photo_path,
                        file_size_bytes, sha256, ml_status, ml_started_at,
                        ml_processed_at, ml_attempts, ml_error, file_synced,
                        supabase_path
        ON photos
        WHEN NEW.row_synced = 1
        BEGIN
            UPDATE photos SET row_synced = 0 WHERE id = NEW.id;
        END;
    """)

    op.execute("""
        CREATE TRIGGER ml_detections_row_synced_reset
        AFTER UPDATE OF top_class, top_confidence, varroa_max_confidence,
                        detections_json, varroa_count, pollen_count,
                        wasp_count, bee_count, inference_ms, model_version,
                        model_hash
        ON ml_detections
        WHEN NEW.row_synced = 1
        BEGIN
            UPDATE ml_detections SET row_synced = 0 WHERE id = NEW.id;
        END;
    """)

    op.execute("""
        CREATE TRIGGER camera_nodes_row_synced_reset
        AFTER UPDATE OF hive_id, api_key_hash, last_seen_at ON camera_nodes
        WHEN NEW.row_synced = 1
        BEGIN
            UPDATE camera_nodes SET row_synced = 0 WHERE device_id = NEW.device_id;
        END;
    """)

    op.execute("""
        CREATE TRIGGER inspections_row_synced_reset
        AFTER UPDATE OF inspected_at, queen_seen, brood_pattern,
                        treatment_type, treatment_notes, notes, updated_at
        ON inspections
        WHEN NEW.row_synced = 1 AND NEW.source != 'cloud'
        BEGIN
            UPDATE inspections SET row_synced = 0 WHERE uuid = NEW.uuid;
        END;
    """)

    op.execute("""
        CREATE TRIGGER alerts_row_synced_reset
        AFTER UPDATE OF acknowledged, acknowledged_at, acknowledged_by,
                        notified_at, source, updated_at
        ON alerts
        WHEN NEW.row_synced = 1 AND NEW.source != 'cloud'
        BEGIN
            UPDATE alerts SET row_synced = 0 WHERE id = NEW.id;
        END;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS hives_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS sensor_readings_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS bee_counts_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS photos_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS ml_detections_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS camera_nodes_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS inspections_row_synced_reset;")
    op.execute("DROP TRIGGER IF EXISTS alerts_row_synced_reset;")
    op.execute("DROP TABLE IF EXISTS ml_detections;")
    op.execute("DROP TABLE IF EXISTS photos;")
    op.execute("DROP TABLE IF EXISTS inspections;")
    op.execute("DROP TABLE IF EXISTS camera_nodes;")
    op.execute("DROP TABLE IF EXISTS sync_state;")
