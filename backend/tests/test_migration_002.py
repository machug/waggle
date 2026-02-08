"""Tests for migration 002: bee_counts table and alert type expansion."""

import sqlite3

import pytest


@pytest.fixture
def db(tmp_path):
    """Create an in-memory-like SQLite DB, run migration 001 then 002, and return it."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")

    # --- Replicate migration 001 schema ---
    conn.executescript("""
        CREATE TABLE hives (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            location    TEXT,
            notes       TEXT,
            sender_mac  TEXT UNIQUE,
            last_seen_at TEXT,
            created_at  TEXT NOT NULL,
            CHECK(id BETWEEN 1 AND 250),
            CHECK(LENGTH(name) BETWEEN 1 AND 64),
            CHECK(location IS NULL OR LENGTH(location) <= 256),
            CHECK(notes IS NULL OR LENGTH(notes) <= 1024),
            CHECK(sender_mac IS NULL OR LENGTH(sender_mac) = 17)
        );

        CREATE TABLE sensor_readings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id      INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            observed_at  TEXT NOT NULL,
            ingested_at  TEXT NOT NULL,
            weight_kg    REAL,
            temp_c       REAL,
            humidity_pct REAL,
            pressure_hpa REAL,
            battery_v    REAL,
            sequence     INTEGER NOT NULL,
            flags        INTEGER NOT NULL DEFAULT 0,
            sender_mac   TEXT NOT NULL,
            CHECK(weight_kg IS NULL OR weight_kg BETWEEN 0 AND 200),
            CHECK(temp_c IS NULL OR temp_c BETWEEN -20 AND 60),
            CHECK(humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100),
            CHECK(pressure_hpa IS NULL OR pressure_hpa BETWEEN 300 AND 1100),
            CHECK(battery_v IS NULL OR battery_v BETWEEN 2.5 AND 4.5),
            CHECK(sequence BETWEEN 0 AND 65535),
            CHECK(flags BETWEEN 0 AND 255),
            CHECK(LENGTH(sender_mac) = 17),
            UNIQUE(hive_id, sequence, observed_at)
        );

        CREATE INDEX idx_readings_hive_time ON sensor_readings(hive_id, observed_at);
        CREATE INDEX idx_readings_time ON sensor_readings(observed_at);

        CREATE TABLE alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id         INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            reading_id      INTEGER REFERENCES sensor_readings(id) ON DELETE SET NULL,
            type            TEXT NOT NULL
                                CHECK(type IN ('POSSIBLE_SWARM','HIGH_TEMP','LOW_TEMP',
                                               'LOW_BATTERY','NO_DATA')),
            severity        TEXT NOT NULL CHECK(severity IN ('high','medium','low')),
            message         TEXT NOT NULL CHECK(LENGTH(message) BETWEEN 1 AND 256),
            acknowledged    INTEGER NOT NULL DEFAULT 0 CHECK(acknowledged IN (0, 1)),
            acknowledged_at TEXT,
            acknowledged_by TEXT CHECK(acknowledged_by IS NULL
                                      OR LENGTH(acknowledged_by) <= 64),
            created_at      TEXT NOT NULL
        );

        CREATE INDEX idx_alerts_hive ON alerts(hive_id, created_at);
        CREATE INDEX idx_alerts_unacked ON alerts(acknowledged, created_at);
    """)

    # --- Apply migration 002 DDL ---
    alert_types_v2 = (
        "'HIGH_TEMP','LOW_TEMP','HIGH_HUMIDITY','LOW_HUMIDITY',"
        "'RAPID_WEIGHT_LOSS','LOW_BATTERY','NO_DATA',"
        "'POSSIBLE_SWARM','ABSCONDING','ROBBING','LOW_ACTIVITY'"
    )

    conn.executescript(f"""
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

        CREATE INDEX idx_bee_counts_hive_time ON bee_counts(hive_id, observed_at DESC);

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

        CREATE TRIGGER bee_counts_no_update
        BEFORE UPDATE ON bee_counts
        BEGIN
            SELECT RAISE(ABORT, 'bee_counts is append-only; updates are not permitted');
        END;

        ALTER TABLE alerts RENAME TO _alerts_old;

        CREATE TABLE alerts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id          INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
            reading_id       INTEGER REFERENCES sensor_readings(id) ON DELETE SET NULL,
            type             TEXT NOT NULL
                                CHECK(type IN ({alert_types_v2})),
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

        INSERT INTO alerts SELECT * FROM _alerts_old;
        DROP TABLE _alerts_old;

        CREATE INDEX idx_alerts_hive ON alerts(hive_id, created_at);
        CREATE INDEX idx_alerts_unacked ON alerts(acknowledged, created_at);
    """)

    yield conn
    conn.close()


def _seed_hive_and_reading(conn):
    """Insert a hive and sensor_reading, return the reading id."""
    conn.execute(
        "INSERT INTO hives (id, name, created_at) VALUES (1, 'Hive A', '2026-02-08T12:00:00.000Z')"
    )
    conn.execute(
        "INSERT INTO sensor_readings "
        "(hive_id, observed_at, ingested_at, sequence, flags, sender_mac) "
        "VALUES (1, '2026-02-08T12:01:00.000Z', '2026-02-08T12:01:00.100Z', "
        "42, 0, 'AA:BB:CC:DD:EE:FF')"
    )
    row = conn.execute("SELECT id FROM sensor_readings WHERE sequence = 42").fetchone()
    conn.commit()
    return row[0]


class TestBeeCountsTableCreated:
    """Verify the bee_counts table exists with the expected structure."""

    def test_table_exists(self, db):
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        assert "bee_counts" in tables

    def test_index_exists(self, db):
        indexes = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='bee_counts'"
            ).fetchall()
        ]
        assert "idx_bee_counts_hive_time" in indexes

    def test_triggers_exist(self, db):
        triggers = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        ]
        assert "bee_counts_validate_insert" in triggers
        assert "bee_counts_no_update" in triggers

    def test_columns_match_spec(self, db):
        # table_xinfo includes generated columns (table_info does not)
        columns = {
            r[1]: r[2]
            for r in db.execute("PRAGMA table_xinfo(bee_counts)").fetchall()
        }
        expected_columns = [
            "id", "reading_id", "hive_id", "observed_at", "ingested_at",
            "period_ms", "bees_in", "bees_out", "net_out", "total_traffic",
            "lane_mask", "stuck_mask", "sequence", "flags", "sender_mac",
        ]
        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"


class TestAlertTypeExpansion:
    """Verify alerts table now accepts Phase 2 alert types and 'high' severity."""

    def test_phase2_alert_types_accepted(self, db):
        db.execute(
            "INSERT INTO hives (id, name, created_at) "
            "VALUES (1, 'Hive A', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()
        phase2_types = [
            "HIGH_TEMP", "LOW_TEMP", "HIGH_HUMIDITY", "LOW_HUMIDITY",
            "RAPID_WEIGHT_LOSS", "LOW_BATTERY", "NO_DATA",
            "POSSIBLE_SWARM", "ABSCONDING", "ROBBING", "LOW_ACTIVITY",
        ]
        for alert_type in phase2_types:
            db.execute(
                "INSERT INTO alerts (hive_id, type, severity, message, created_at) "
                "VALUES (1, ?, 'medium', 'test message', '2026-02-08T12:00:00.000Z')",
                (alert_type,),
            )
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        assert count == len(phase2_types)

    def test_invalid_alert_type_rejected(self, db):
        db.execute(
            "INSERT INTO hives (id, name, created_at) "
            "VALUES (1, 'Hive A', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO alerts (hive_id, type, severity, message, created_at) "
                "VALUES (1, 'INVALID_TYPE', 'medium', 'test', '2026-02-08T12:00:00.000Z')"
            )

    def test_high_severity_accepted(self, db):
        db.execute(
            "INSERT INTO hives (id, name, created_at) "
            "VALUES (1, 'Hive A', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()
        db.execute(
            "INSERT INTO alerts (hive_id, type, severity, message, created_at) "
            "VALUES (1, 'HIGH_TEMP', 'high', 'test message', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()

    def test_critical_severity_accepted(self, db):
        db.execute(
            "INSERT INTO hives (id, name, created_at) "
            "VALUES (1, 'Hive A', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()
        db.execute(
            "INSERT INTO alerts (hive_id, type, severity, message, created_at) "
            "VALUES (1, 'HIGH_TEMP', 'critical', 'test message', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()


class TestGeneratedColumns:
    """Verify net_out and total_traffic are computed correctly."""

    def test_net_out_computed(self, db):
        reading_id = _seed_hive_and_reading(db)
        db.execute(
            "INSERT INTO bee_counts "
            "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
            "lane_mask, stuck_mask, sequence, flags, sender_mac) "
            "VALUES (?, 1, '2026-02-08T12:01:00.000Z', 5000, 10, 25, "
            "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')",
            (reading_id,),
        )
        db.commit()
        row = db.execute("SELECT net_out, total_traffic FROM bee_counts").fetchone()
        assert row[0] == 15, f"net_out should be 25 - 10 = 15, got {row[0]}"
        assert row[1] == 35, f"total_traffic should be 10 + 25 = 35, got {row[1]}"

    def test_net_out_negative(self, db):
        reading_id = _seed_hive_and_reading(db)
        db.execute(
            "INSERT INTO bee_counts "
            "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
            "lane_mask, stuck_mask, sequence, flags, sender_mac) "
            "VALUES (?, 1, '2026-02-08T12:01:00.000Z', 5000, 30, 5, "
            "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')",
            (reading_id,),
        )
        db.commit()
        row = db.execute("SELECT net_out, total_traffic FROM bee_counts").fetchone()
        assert row[0] == -25, f"net_out should be 5 - 30 = -25, got {row[0]}"
        assert row[1] == 35, f"total_traffic should be 30 + 5 = 35, got {row[1]}"


class TestIntegrityTrigger:
    """Verify bee_counts_validate_insert rejects mismatched data."""

    def test_mismatched_hive_id_rejected(self, db):
        reading_id = _seed_hive_and_reading(db)
        # Create hive 2 so the FK passes but the trigger catches the mismatch
        db.execute(
            "INSERT INTO hives (id, name, created_at) "
            "VALUES (2, 'Hive B', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="hive_id mismatch"):
            db.execute(
                "INSERT INTO bee_counts "
                "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
                "lane_mask, stuck_mask, sequence, flags, sender_mac) "
                "VALUES (?, 2, '2026-02-08T12:01:00.000Z', 5000, 10, 5, "
                "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')",
                (reading_id,),
            )

    def test_mismatched_observed_at_rejected(self, db):
        reading_id = _seed_hive_and_reading(db)
        with pytest.raises(sqlite3.IntegrityError, match="observed_at mismatch"):
            db.execute(
                "INSERT INTO bee_counts "
                "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
                "lane_mask, stuck_mask, sequence, flags, sender_mac) "
                "VALUES (?, 1, '2026-02-08T12:02:00.000Z', 5000, 10, 5, "
                "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')",
                (reading_id,),
            )

    def test_mismatched_sequence_rejected(self, db):
        reading_id = _seed_hive_and_reading(db)
        with pytest.raises(sqlite3.IntegrityError, match="sequence mismatch"):
            db.execute(
                "INSERT INTO bee_counts "
                "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
                "lane_mask, stuck_mask, sequence, flags, sender_mac) "
                "VALUES (?, 1, '2026-02-08T12:01:00.000Z', 5000, 10, 5, "
                "255, 0, 99, 0, 'AA:BB:CC:DD:EE:FF')",
                (reading_id,),
            )

    def test_nonexistent_reading_id_rejected(self, db):
        db.execute(
            "INSERT INTO hives (id, name, created_at) "
            "VALUES (1, 'Hive A', '2026-02-08T12:00:00.000Z')"
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="reading_id not found"):
            db.execute(
                "INSERT INTO bee_counts "
                "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
                "lane_mask, stuck_mask, sequence, flags, sender_mac) "
                "VALUES (9999, 1, '2026-02-08T12:01:00.000Z', 5000, 10, 5, "
                "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')"
            )

    def test_valid_insert_succeeds(self, db):
        reading_id = _seed_hive_and_reading(db)
        db.execute(
            "INSERT INTO bee_counts "
            "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
            "lane_mask, stuck_mask, sequence, flags, sender_mac) "
            "VALUES (?, 1, '2026-02-08T12:01:00.000Z', 5000, 10, 5, "
            "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')",
            (reading_id,),
        )
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM bee_counts").fetchone()[0]
        assert count == 1


class TestAppendOnlyTrigger:
    """Verify bee_counts_no_update prevents modifications."""

    def test_update_rejected(self, db):
        reading_id = _seed_hive_and_reading(db)
        db.execute(
            "INSERT INTO bee_counts "
            "(reading_id, hive_id, observed_at, period_ms, bees_in, bees_out, "
            "lane_mask, stuck_mask, sequence, flags, sender_mac) "
            "VALUES (?, 1, '2026-02-08T12:01:00.000Z', 5000, 10, 5, "
            "255, 0, 42, 0, 'AA:BB:CC:DD:EE:FF')",
            (reading_id,),
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE bee_counts SET bees_in = 20 WHERE id = 1")
