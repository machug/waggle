-- Waggle Phase 3 Supabase Schema
-- Mirrors local SQLite schema with Postgres-native types

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS hives (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    location TEXT,
    notes TEXT,
    sender_mac TEXT UNIQUE,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_hive_id_range CHECK (id BETWEEN 1 AND 250),
    CONSTRAINT ck_hive_name_length CHECK (LENGTH(name) BETWEEN 1 AND 64),
    CONSTRAINT ck_hive_location_length CHECK (location IS NULL OR LENGTH(location) <= 256),
    CONSTRAINT ck_hive_notes_length CHECK (notes IS NULL OR LENGTH(notes) <= 1024),
    CONSTRAINT ck_hive_mac_format CHECK (sender_mac IS NULL OR LENGTH(sender_mac) = 17)
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id SERIAL PRIMARY KEY,
    hive_id INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    weight_kg REAL,
    temp_c REAL,
    humidity_pct REAL,
    pressure_hpa REAL,
    battery_v REAL,
    sequence INTEGER NOT NULL,
    flags INTEGER NOT NULL DEFAULT 0,
    sender_mac TEXT NOT NULL,
    CONSTRAINT ck_reading_weight CHECK (weight_kg IS NULL OR weight_kg BETWEEN 0 AND 200),
    CONSTRAINT ck_reading_temp CHECK (temp_c IS NULL OR temp_c BETWEEN -20 AND 60),
    CONSTRAINT ck_reading_humidity CHECK (humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_reading_pressure CHECK (pressure_hpa IS NULL OR pressure_hpa BETWEEN 300 AND 1100),
    CONSTRAINT ck_reading_battery CHECK (battery_v IS NULL OR battery_v BETWEEN 2.5 AND 4.5),
    CONSTRAINT ck_reading_sequence CHECK (sequence BETWEEN 0 AND 65535),
    CONSTRAINT ck_reading_flags CHECK (flags BETWEEN 0 AND 255),
    CONSTRAINT ck_reading_mac_format CHECK (LENGTH(sender_mac) = 17),
    CONSTRAINT uq_readings_dedup UNIQUE (hive_id, sequence, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_readings_hive_time ON sensor_readings(hive_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_readings_time ON sensor_readings(observed_at);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    hive_id INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    details_json TEXT,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    notified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'local',
    CONSTRAINT ck_alert_type CHECK (type IN (
        'HIGH_TEMP','LOW_TEMP','HIGH_HUMIDITY','LOW_HUMIDITY',
        'RAPID_WEIGHT_LOSS','LOW_BATTERY','NO_DATA','POSSIBLE_SWARM',
        'ABSCONDING','ROBBING','LOW_ACTIVITY','VARROA_DETECTED',
        'VARROA_HIGH_LOAD','VARROA_RISING','WASP_ATTACK'
    )),
    CONSTRAINT ck_alert_severity CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT ck_alert_message_length CHECK (LENGTH(message) BETWEEN 1 AND 256),
    CONSTRAINT ck_alert_ack_by_length CHECK (acknowledged_by IS NULL OR LENGTH(acknowledged_by) <= 64)
);

CREATE INDEX IF NOT EXISTS idx_alerts_hive_type ON alerts(hive_id, type, created_at DESC);

CREATE TABLE IF NOT EXISTS bee_counts (
    id SERIAL PRIMARY KEY,
    reading_id INTEGER NOT NULL UNIQUE REFERENCES sensor_readings(id) ON DELETE CASCADE,
    hive_id INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    period_ms INTEGER NOT NULL,
    bees_in INTEGER NOT NULL,
    bees_out INTEGER NOT NULL,
    net_out INTEGER NOT NULL,
    total_traffic INTEGER NOT NULL,
    lane_mask INTEGER NOT NULL,
    stuck_mask INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    flags INTEGER NOT NULL DEFAULT 0,
    sender_mac TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bee_counts_hive_time ON bee_counts(hive_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS camera_nodes (
    device_id TEXT PRIMARY KEY,
    hive_id INTEGER NOT NULL REFERENCES hives(id),
    api_key_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS photos (
    id SERIAL PRIMARY KEY,
    hive_id INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
    device_id TEXT NOT NULL REFERENCES camera_nodes(device_id),
    boot_id INTEGER NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    captured_at_source TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sequence INTEGER NOT NULL,
    photo_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 800,
    height INTEGER NOT NULL DEFAULT 600,
    ml_status TEXT NOT NULL DEFAULT 'pending',
    ml_started_at TIMESTAMPTZ,
    ml_processed_at TIMESTAMPTZ,
    ml_attempts INTEGER NOT NULL DEFAULT 0,
    ml_error TEXT,
    supabase_path TEXT,
    CONSTRAINT ck_photo_file_size CHECK (file_size_bytes > 0),
    CONSTRAINT ck_photo_ml_status CHECK (ml_status IN ('pending', 'processing', 'completed', 'failed')),
    CONSTRAINT ck_photo_captured_source CHECK (captured_at_source IN ('device_ntp', 'device_rtc', 'ingested')),
    CONSTRAINT uq_photos_device_boot_seq UNIQUE (device_id, boot_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_photos_hive_time ON photos(hive_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_photos_ml_status ON photos(ml_status);
CREATE INDEX IF NOT EXISTS idx_photos_sha256 ON photos(sha256);

CREATE TABLE IF NOT EXISTS ml_detections (
    id SERIAL PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    hive_id INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
    detected_at TIMESTAMPTZ NOT NULL,
    top_class TEXT NOT NULL,
    top_confidence REAL NOT NULL,
    detections_json TEXT NOT NULL DEFAULT '[]',
    varroa_count INTEGER NOT NULL DEFAULT 0,
    pollen_count INTEGER NOT NULL DEFAULT 0,
    wasp_count INTEGER NOT NULL DEFAULT 0,
    bee_count INTEGER NOT NULL DEFAULT 0,
    varroa_max_confidence REAL NOT NULL DEFAULT 0.0,
    inference_ms INTEGER NOT NULL,
    model_version TEXT NOT NULL DEFAULT 'yolov8n-waggle-v1',
    model_hash TEXT NOT NULL,
    CONSTRAINT ck_detection_class CHECK (top_class IN ('varroa', 'pollen', 'wasp', 'bee', 'normal')),
    CONSTRAINT ck_detection_confidence CHECK (top_confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT ck_detection_varroa_conf CHECK (varroa_max_confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT ck_detection_inference_ms CHECK (inference_ms > 0)
);

CREATE INDEX IF NOT EXISTS idx_detections_hive_time ON ml_detections(hive_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_detections_class ON ml_detections(hive_id, top_class);

CREATE TABLE IF NOT EXISTS inspections (
    uuid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hive_id INTEGER NOT NULL REFERENCES hives(id) ON DELETE RESTRICT,
    inspected_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    queen_seen BOOLEAN NOT NULL DEFAULT FALSE,
    brood_pattern TEXT,
    treatment_type TEXT,
    treatment_notes TEXT,
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'local',
    CONSTRAINT ck_inspection_queen_seen CHECK (queen_seen IN (TRUE, FALSE)),
    CONSTRAINT ck_inspection_brood CHECK (brood_pattern IN ('good', 'patchy', 'poor') OR brood_pattern IS NULL),
    CONSTRAINT ck_inspection_source CHECK (source IN ('local', 'cloud'))
);

CREATE INDEX IF NOT EXISTS idx_inspections_hive_time ON inspections(hive_id, inspected_at DESC);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ============================================================
-- RPC: Last-Write-Wins Inspection Upsert
-- ============================================================

CREATE OR REPLACE FUNCTION upsert_inspection_lww(
    p_uuid UUID,
    p_hive_id INTEGER,
    p_inspected_at TIMESTAMPTZ,
    p_created_at TIMESTAMPTZ,
    p_updated_at TIMESTAMPTZ,
    p_queen_seen BOOLEAN,
    p_brood_pattern TEXT DEFAULT NULL,
    p_treatment_type TEXT DEFAULT NULL,
    p_treatment_notes TEXT DEFAULT NULL,
    p_notes TEXT DEFAULT NULL,
    p_source TEXT DEFAULT 'local'
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO inspections (
        uuid, hive_id, inspected_at, created_at, updated_at,
        queen_seen, brood_pattern, treatment_type, treatment_notes, notes, source
    ) VALUES (
        p_uuid, p_hive_id, p_inspected_at, p_created_at, p_updated_at,
        p_queen_seen, p_brood_pattern, p_treatment_type, p_treatment_notes, p_notes, p_source
    )
    ON CONFLICT (uuid) DO UPDATE SET
        hive_id = EXCLUDED.hive_id,
        inspected_at = EXCLUDED.inspected_at,
        updated_at = EXCLUDED.updated_at,
        queen_seen = EXCLUDED.queen_seen,
        brood_pattern = EXCLUDED.brood_pattern,
        treatment_type = EXCLUDED.treatment_type,
        treatment_notes = EXCLUDED.treatment_notes,
        notes = EXCLUDED.notes,
        source = EXCLUDED.source
    WHERE inspections.updated_at < EXCLUDED.updated_at;
END;
$$;

-- ============================================================
-- Trigger: Auto-set source='cloud' for dashboard writes
-- ============================================================

CREATE OR REPLACE FUNCTION handle_inspection_write()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- If no source specified or source is not being set by sync service,
    -- default to 'cloud' for dashboard-originated writes
    IF NEW.source IS NULL OR NEW.source = '' THEN
        NEW.source := 'cloud';
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER tr_inspection_write
    BEFORE INSERT OR UPDATE ON inspections
    FOR EACH ROW
    EXECUTE FUNCTION handle_inspection_write();

-- ============================================================
-- Row-Level Security (RLS)
-- ============================================================

ALTER TABLE hives ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensor_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE bee_counts ENABLE ROW LEVEL SECURITY;
ALTER TABLE camera_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspections ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_state ENABLE ROW LEVEL SECURITY;

-- Service role (used by Pi sync) has full access
-- These policies use the service_role which bypasses RLS, but we add
-- explicit policies for authenticated role (dashboard users)

-- Authenticated users: full CRUD on all tables
CREATE POLICY "authenticated_full_access" ON hives FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON sensor_readings FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON alerts FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON bee_counts FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON camera_nodes FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON photos FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON ml_detections FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON inspections FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_full_access" ON sync_state FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- No anon access (RLS enabled with no anon policies = deny all for anon)

-- ============================================================
-- Storage: Private photos bucket
-- ============================================================

INSERT INTO storage.buckets (id, name, public)
VALUES ('photos', 'photos', false)
ON CONFLICT (id) DO NOTHING;
