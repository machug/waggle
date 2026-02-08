# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-02-08

### Added

**Backend**
- ESP32-CAM photo upload endpoint with multipart JPEG handling and auto-rotation
- Photo serving endpoint with optional signed URL support
- YOLOv8-nano ML worker with inference loop, crash recovery, and stale photo cleanup
- Varroa mite load tracking with daily aggregation and cross-hive overview
- Inspection CRUD with UUID primary keys for bidirectional sync
- Cloud sync service: push (readings, alerts, photos), pull (inspections, alert acks)
- Supabase schema with RLS policies, RPC functions, and storage buckets
- Webhook notification dispatcher with HMAC signing
- Weather endpoint proxying external API
- Admin key authentication for camera registration
- 4 ML-based alert rules: VARROA_HIGH_LOAD, VARROA_RISING, QUEEN_MISSING, PEST_DETECTED
- Photo pruning service with configurable retention
- Phase 3 Prometheus metrics (inference latency, sync lag, photo count)
- 495 tests total (198 new), 0 ruff warnings

**Dashboard**
- Dual-mode data layer: local (SvelteKit proxy) or cloud (Supabase direct)
- PhotoFeed component with responsive grid, filter buttons, and ML status badges
- PhotoDetail overlay with SVG bounding box visualization (color-coded by class)
- VarroaChart with Chart.js line graph, shaded severity zones, and 30/60/90 day toggle
- VarroaTable for cross-hive mite load comparison
- InspectionForm for manual hive inspection logging
- InspectionTimeline with chronological history and source badges
- WeatherOverlay widget with current conditions
- LoginForm for Supabase cloud authentication
- Signed URL helper with client-side batch caching
- Varroa tracking page (/varroa) with summary cards
- Inspection log page (/inspections) with form and timeline
- Cloud login page (/login) for remote access

**Firmware**
- ESP32-CAM node firmware: deep sleep wake cycle, photo capture, WiFi HTTP POST upload
- NVS configuration for hive_id, WiFi credentials, API endpoint
- AI-Thinker ESP32-CAM pin configuration with PSRAM support

**Infrastructure**
- systemd units for ML worker, sync service, and notification dispatcher
- Supabase project configuration for local development
- Updated .env.example with all Phase 3 variables

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
