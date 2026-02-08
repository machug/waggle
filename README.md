# Waggle

Hobbyist beehive monitoring system with ESP32 sensor nodes, Raspberry Pi hub, and SvelteKit dashboard.

## Architecture

```
ESP32 Sensor Nodes (deep/light sleep, wake every 60s)
    │ ESP-NOW (32-byte Phase 1 / 48-byte Phase 2 payload)
    ▼
ESP32 Bridge (USB serial, COBS framing)
    │ Serial /dev/ttyUSB0
    ▼
Pi Hub: Bridge Service (Python)
    │ MQTT (mosquitto, localhost:1883)
    ▼
Pi Hub: Worker Service (Python)
    │ Validate, dedup, store (sensor_readings + bee_counts), alert
    ▼
SQLite (WAL mode)
    │
    ├──▶ Pi Hub: REST API (FastAPI, http://127.0.0.1:8000)
    │        │
    │        ▼
    │    SvelteKit Dashboard (http://pi-address:3000)
    │        │ Server-side API proxy OR Supabase direct
    │        ▼
    │    Browser
    │
    ├──▶ Pi Hub: ML Worker (YOLOv8-nano inference)
    │        │ Process photos → detect bees, varroa, wasps
    │        ▼
    │    Photo Storage (/var/lib/waggle/photos/)
    │
    └──▶ Pi Hub: Cloud Sync Service
             │ Push readings/alerts/photos, pull inspections
             ▼
         Supabase (Postgres + Storage + Auth)

ESP32-CAM Nodes (deep sleep, wake every 15min)
    │ WiFi HTTP POST (multipart JPEG)
    ▼
Pi Hub: REST API (/api/photos/upload)
```

## Components

| Component | Tech | Location |
|-----------|------|----------|
| Sensor firmware | C++ / PlatformIO / Arduino | `firmware/sensor/` |
| Bridge firmware | C++ / PlatformIO / Arduino | `firmware/bridge/` |
| Bridge service | Python 3.13 | `backend/waggle/services/bridge.py` |
| Worker service | Python 3.13 | `backend/waggle/services/ingestion.py` |
| REST API | FastAPI + SQLAlchemy 2.0 async | `backend/waggle/` |
| Dashboard | SvelteKit 2 + Tailwind CSS 4 | `dashboard/` |
| Camera firmware | C++ / PlatformIO / Arduino | `firmware/camera-node/` |
| ML worker | Python 3.13 + YOLOv8-nano | `backend/waggle/services/ml_worker.py` |
| Cloud sync | Python 3.13 + Supabase | `backend/waggle/services/sync.py` |
| Deployment | systemd + Mosquitto | `deploy/` |

## Quick Start (Development)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Edit API_KEY
python -m waggle api
```

API runs at http://127.0.0.1:8000. Docs at http://127.0.0.1:8000/api/docs.

### Dashboard

```bash
cd dashboard
npm install
echo "WAGGLE_API_URL=http://127.0.0.1:8000" > .env
echo "WAGGLE_API_KEY=dev-waggle-key-2026" >> .env
npm run dev
```

Dashboard runs at http://localhost:5173.

### Firmware

```bash
# Sensor node
cd firmware/sensor
pio run -t upload

# Bridge
cd firmware/bridge
pio run -t upload
```

### Camera Firmware

```bash
cd firmware/camera-node
# Edit src/config.h for your WiFi and API settings
pio run -t upload
```

## Pi Deployment

```bash
sudo ./scripts/install.sh
# Review /etc/waggle/.env
sudo systemctl start waggle-bridge waggle-worker waggle-api waggle-ml waggle-sync
```

See `deploy/` for systemd units and Mosquitto config.

## API Endpoints

All endpoints require `X-API-Key` header unless noted.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/hub/status` | No | Hub health and stats |
| GET | `/api/hives` | Yes | List hives with latest reading |
| POST | `/api/hives` | Yes | Create hive |
| GET | `/api/hives/{id}` | Yes | Get hive details |
| PATCH | `/api/hives/{id}` | Yes | Update hive |
| DELETE | `/api/hives/{id}` | Yes | Delete hive |
| GET | `/api/hives/{id}/readings` | Yes | Readings (raw/hourly/daily) |
| GET | `/api/hives/{id}/readings/latest` | Yes | Latest reading |
| GET | `/api/hives/{id}/traffic` | Yes | Traffic history (raw/hourly/daily) |
| GET | `/api/hives/{id}/traffic/latest` | Yes | Latest traffic reading |
| GET | `/api/hives/{id}/traffic/summary` | Yes | Traffic summary with activity score |
| GET | `/api/alerts` | Yes | List alerts (filterable) |
| PATCH | `/api/alerts/{id}/acknowledge` | Yes | Acknowledge alert |
| POST | `/api/admin/camera-nodes` | Admin | Register camera node |
| POST | `/api/photos/upload` | Admin | Upload photo from camera |
| GET | `/api/photos/{id}/image` | Yes | Serve photo image |
| GET | `/api/hives/{id}/photos` | Yes | List photos for hive |
| GET | `/api/hives/{id}/detections` | Yes | ML detection results |
| GET | `/api/hives/{id}/varroa` | Yes | Varroa mite load history |
| GET | `/api/varroa/overview` | Yes | Cross-hive varroa summary |
| POST | `/api/inspections` | Yes | Create inspection |
| PUT | `/api/inspections/{uuid}` | Yes | Update inspection |
| GET | `/api/hives/{id}/inspections` | Yes | List hive inspections |
| GET | `/api/weather/current` | Yes | Weather conditions |
| GET | `/api/sync/status` | Yes | Cloud sync status |

## Alert Rules

### Phase 1 (Environmental)

| Type | Condition | Severity | Cooldown |
|------|-----------|----------|----------|
| POSSIBLE_SWARM | Weight drop >2kg in 1h (weight only) | high | 24h |
| HIGH_TEMP | temp_c > 40 | medium | 4h |
| LOW_TEMP | temp_c < 5 | medium | 4h |
| LOW_BATTERY | battery_v < 3.3 | low | 24h |
| NO_DATA | No reading for >15min | low | 1h |

### Phase 2 (Correlation — requires bee counting sensors)

| Type | Condition | Severity | Cooldown |
|------|-----------|----------|----------|
| POSSIBLE_SWARM | Weight drop >1.5kg AND net_out >500 in 1h | critical | 12h |
| ABSCONDING | Weight drop >2kg AND net_out >400 over 2h | critical | 24h |
| ROBBING | High traffic AND net inflow AND weight loss | high | 4h |
| LOW_ACTIVITY | Traffic <20% of 7-day average | medium | 24h |

### Phase 3 (Vision -- requires ESP32-CAM + ML worker)

| Type | Condition | Severity | Cooldown |
|------|-----------|----------|----------|
| VARROA_HIGH_LOAD | Mite load >3 per 100 bees | high | 24h |
| VARROA_RISING | Mite load rising >50% over 7 days | medium | 48h |
| QUEEN_MISSING | No queen detected in 14+ days | high | 72h |
| PEST_DETECTED | Wasp/hornet detected in frame | medium | 4h |

## Testing

```bash
# Backend (495 tests)
cd backend && pytest tests/ -v

# Firmware COBS tests
cd firmware/bridge && pio test -e native

# Firmware payload tests
cd firmware/sensor && pio test -e native

# Lint
cd backend && ruff check .
```

## Project Phases

- **Phase 1: Sensor Foundation** -- ESP32 nodes, Pi hub, REST API, dashboard
- **Phase 2: Bee Counting** -- IR beam-break sensors, traffic API, correlation alerts
- **Phase 3: Vision Intelligence** (current) -- ESP32-CAM, ML inference, cloud sync, varroa tracking

## License

Private project.
