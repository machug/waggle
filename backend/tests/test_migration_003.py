"""Test Phase 3 migration creates vision + cloud sync tables."""
import os
import sqlite3

import pytest
from alembic.command import upgrade
from alembic.config import Config


@pytest.fixture
def alembic_config(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    # env.py reads DB_PATH to build the SQLAlchemy URL; override it so
    # migrations target the temporary test database.
    monkeypatch.setenv("DB_PATH", str(db_path))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg, db_path


def test_migration_creates_camera_nodes(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='camera_nodes'"
    ).fetchone()[0]
    assert "device_id" in sql
    assert "api_key_hash" in sql
    assert "row_synced" in sql
    conn.close()


def test_migration_creates_photos(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='photos'"
    ).fetchone()[0]
    assert "ml_status" in sql
    assert "file_synced" in sql
    assert "supabase_path" in sql
    assert "sha256" in sql
    conn.close()


def test_migration_creates_ml_detections(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='ml_detections'"
    ).fetchone()[0]
    assert "varroa_max_confidence" in sql
    assert "model_hash" in sql
    assert "ON DELETE CASCADE" in sql
    conn.close()


def test_migration_creates_inspections(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='inspections'"
    ).fetchone()[0]
    assert "uuid" in sql
    assert "source" in sql
    assert "row_synced" in sql
    conn.close()


def test_migration_creates_sync_state(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='sync_state'"
    ).fetchone()[0]
    assert "key" in sql
    conn.close()


def test_alerts_expanded_with_ml_types(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='alerts'"
    ).fetchone()[0]
    for t in ["VARROA_DETECTED", "VARROA_HIGH_LOAD", "VARROA_RISING", "WASP_ATTACK"]:
        assert t in sql
    assert "notified_at" in sql
    assert "updated_at" in sql
    assert "source" in sql
    assert "details_json" in sql
    conn.close()


def test_hives_has_row_synced(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(hives)")]
    assert "row_synced" in cols
    conn.close()


def test_sensor_readings_has_row_synced(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sensor_readings)")]
    assert "row_synced" in cols
    conn.close()


def test_row_synced_triggers_exist(alembic_config):
    cfg, db_path = alembic_config
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    triggers = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    ]
    expected = [
        "hives_row_synced_reset",
        "sensor_readings_row_synced_reset",
        "bee_counts_row_synced_reset",
        "photos_row_synced_reset",
        "ml_detections_row_synced_reset",
        "camera_nodes_row_synced_reset",
        "inspections_row_synced_reset",
        "alerts_row_synced_reset",
    ]
    for t in expected:
        assert t in triggers, f"Missing trigger: {t}"
    conn.close()


def test_existing_alerts_preserved(alembic_config):
    """Existing alerts survive migration with notified_at = created_at."""
    cfg, db_path = alembic_config
    upgrade(cfg, "002")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO hives (id, name, created_at) "
        "VALUES (1, 'Test', '2026-02-08T00:00:00.000Z')"
    )
    # v002 alerts table has: id, hive_id, reading_id, type, severity,
    # message, acknowledged, acknowledged_at, acknowledged_by, created_at
    conn.execute(
        "INSERT INTO alerts (hive_id, type, severity, message, "
        "created_at, reading_id) VALUES "
        "(1, 'HIGH_TEMP', 'medium', 'Hot', "
        "'2026-02-08T12:00:01.000Z', NULL)"
    )
    conn.commit()
    conn.close()
    upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT notified_at, updated_at, source, details_json, observed_at FROM alerts"
    ).fetchone()
    # observed_at = created_at (fallback since v002 had no observed_at)
    assert row[0] == "2026-02-08T12:00:01.000Z"  # notified_at = created_at
    assert row[1] == "2026-02-08T12:00:01.000Z"  # updated_at = created_at
    assert row[2] == "local"
    assert row[3] is None  # details_json = NULL (v002 had no details column)
    assert row[4] == "2026-02-08T12:00:01.000Z"  # observed_at = created_at
    conn.close()
