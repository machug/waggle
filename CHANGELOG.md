# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
