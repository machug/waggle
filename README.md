# Waggle

Hobbyist beehive monitoring system with ESP32 sensor nodes, Raspberry Pi hub, and SvelteKit dashboard.

## Architecture

```
ESP32 Sensor Nodes (deep sleep, wake every 60s)
    │ ESP-NOW (32-byte payload)
    ▼
ESP32 Bridge (USB serial, COBS framing)
    │ Serial /dev/ttyUSB0
    ▼
Pi Hub: Bridge Service (Python)
    │ MQTT (mosquitto, localhost:1883)
    ▼
Pi Hub: Worker Service (Python)
    │ Validate, dedup, store, alert
    ▼
SQLite (WAL mode)
    │
    ▼
Pi Hub: REST API (FastAPI)
    │ http://127.0.0.1:8000
    ▼
SvelteKit Dashboard
    │ Server-side API proxy (hides API key)
    ▼
Browser (http://pi-address:3000)
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

## Pi Deployment

```bash
sudo ./scripts/install.sh
# Review /etc/waggle/.env
sudo systemctl start waggle-bridge waggle-worker waggle-api
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
| GET | `/api/alerts` | Yes | List alerts (filterable) |
| PATCH | `/api/alerts/{id}/acknowledge` | Yes | Acknowledge alert |

## Alert Rules

| Type | Condition | Severity | Cooldown |
|------|-----------|----------|----------|
| POSSIBLE_SWARM | Weight drop >2kg in 1h | high | 24h |
| HIGH_TEMP | temp_c > 40 | medium | 4h |
| LOW_TEMP | temp_c < 5 | medium | 4h |
| LOW_BATTERY | battery_v < 3.3 | low | 24h |
| NO_DATA | No reading for >15min | low | 1h |

## Testing

```bash
# Backend (186 tests)
cd backend && pytest tests/ -v

# Firmware COBS tests
cd firmware/bridge && pio test -e native

# Firmware payload tests
cd firmware/sensor && pio test -e native

# Lint
cd backend && ruff check .
```

## Project Phases

- **Phase 1: Sensor Foundation** (current) -- ESP32 nodes, Pi hub, REST API, dashboard
- **Phase 2: Bee Counting** -- IR sensors, WebSocket live updates
- **Phase 3: Vision Intelligence** -- ESP32-CAM, cloud sync, ML inference

## License

Private project.
