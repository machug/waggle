# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-08

### Added

**Backend**
- `bee_counts` table with Alembic migration, generated columns (net_out, total_traffic), and append-only trigger
- BeeCount SQLAlchemy model with computed columns
- Pydantic traffic schemas (TrafficRecordOut, TrafficAggregateOut, TrafficSummaryOut, LatestTrafficOut)
- 48-byte Phase 2 payload deserializer (bees_in, bees_out, period_ms, lane_mask, stuck_mask)
- Bridge service support for 54-byte frames (6 MAC + 48 payload)
- Dual-table worker ingestion: sensor_readings + bee_counts in single transaction for msg_type=2
- Traffic API router with 3 endpoints: history (raw/hourly/daily), latest, summary with activity score
- Hive list/detail extended with latest_traffic and activity_score_today
- Hub status extended with traffic_readings_24h, phase2_nodes_active, stuck_lanes_total
- 4 correlation alert rules: POSSIBLE_SWARM (critical), ABSCONDING (critical), ROBBING (high), LOW_ACTIVITY (medium)
- Phase 2 Prometheus metrics: traffic_ingested, traffic_dropped, correlation_alerts_fired counters; stuck_lanes_current gauge
- Phase 2 integration tests (full pipeline, mixed fleet, correlation alert)
- 297 tests total (111 new), 0 ruff warnings

**Dashboard**
- TrafficChart component (stacked bar: bees in/out with net line overlay)
- DailySummaryChart component (30-day line graph)
- ActivityHeatmap component (7-day x 24-hour CSS grid)
- TrafficIndicator mini sparkline for hive cards
- ActivityBadge (Quiet/Active/Busy) based on activity score
- HiveCard extended with traffic indicators and critical alert pulse border
- Hive detail page traffic section with hourly chart and heatmap
- AlertEvidence expandable component for correlation alert forensics
- Alerts page updated with Phase 2 types (ABSCONDING, ROBBING, LOW_ACTIVITY) and critical severity
- Apiary overview with critical alert indicators

**Firmware**
- Bee counter ISR module with 4-lane state machines and direction detection
- 48-byte Phase 2 payload format (msg_type=0x02)
- Light sleep mode for ISR-driven counting
- Bridge firmware expanded COBS buffer (54-byte frame support)

## [0.1.0] - 2026-02-08

### Added

**Backend**
- FastAPI REST API with full CRUD for hives, readings, and alerts
- API key authentication with constant-time comparison
- SQLAlchemy 2.0 async models with SQLite WAL mode
- Pydantic v2 request/response schemas
- Worker ingestion service with 14-step validation pipeline
- Two-layer deduplication (in-memory LRU + DB unique index)
- Alert engine with 5 rules: POSSIBLE_SWARM, HIGH_TEMP, LOW_TEMP, LOW_BATTERY, NO_DATA
- Bridge service for serial COBS frame processing
- CRC-8, COBS, and binary payload utilities
- Structured logging (structlog JSON)
- Prometheus metrics for API, bridge, and worker
- Heartbeat health monitoring with atomic file writes
- Alembic database migrations with SQLite batch mode
- Timestamp utilities with validation and skew checking
- 186 tests (unit + integration), 0 ruff warnings

**Dashboard**
- SvelteKit 2 + Svelte 5 + Tailwind CSS 4
- Server-side API proxy (API key never reaches browser)
- Apiary overview with hive cards and 60s polling
- Hive detail page with Chart.js weight/environment/battery charts
- Alerts page with filtering and acknowledge
- Settings page with hive CRUD management
- Responsive amber/honey themed layout with PWA manifest
- Hub online/offline status indicator

**Firmware**
- ESP32 sensor node firmware (deep sleep, HX711, BME280, ESP-NOW TX)
- ESP32 bridge firmware (ESP-NOW RX, COBS encode, USB serial TX)
- Serial provisioning (SET_ID, SET_BRIDGE, TARE, CALIBRATE)
- CRC-8 and COBS implementations matching Python backend

**Infrastructure**
- systemd service units for bridge, worker, and API
- Mosquitto MQTT broker configuration
- Pi install script with security hardening
- GitHub Actions CI for backend tests and dashboard build
