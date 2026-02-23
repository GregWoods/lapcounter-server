# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scalextric digital lap counter and race management system. A 4-layer Docker-based architecture running on Raspberry Pi that counts laps, manages races, and serves a real-time leaderboard via web browser. Designed to work fully offline (Pi acts as WiFi AP).

## Architecture

```
GPIO (Layer 1) → publishes "car_timestamp" to MQTT
LapData (Layer 2) → subscribes car_timestamp, calculates lap times, publishes "lap" to MQTT
API (Layer 3) → FastAPI + PostgreSQL REST backend
React (Layer 4) → Vite + React SPA, receives lap data via MQTT WebSocket
```

- **mosquitto/** - Eclipse Mosquitto MQTT broker config (bridging all layers)
- **gpio/** - Raspberry Pi GPIO reader (has `Dockerfile.Mocked` for dev without hardware)
- **lapdata/** - MQTT subscriber that transforms raw car_timestamp into lap data
- **api/app/** - FastAPI backend (SQLModel ORM, PostgreSQL)
- **react/src/** - React 18 frontend (Vite, React Bootstrap, Ant Design, mqtt.js)

## Development Commands

### Start full stack (Docker)
```
docker compose -f compose.dev.yaml up --build
```
- React: http://localhost:8088 (hot module reloading)
- API: http://localhost:8000 (auto-reload via uvicorn)
- API docs (Swagger): http://localhost:8000/docs
- PgAdmin: http://localhost:5050

### Run Python tests
```
python -m pytest api/app/test_next_race.py
```
Run a single test:
```
python -m pytest api/app/test_next_race.py::test_lane_preference
```

### Lint React code
```
cd react && npm run lint
```
ESLint is configured with `--max-warnings 0` (zero tolerance).

### Production build & push
```powershell
./build-and-push.ps1
```
Builds multi-platform images (amd64, arm/v7, arm64) and pushes to DockerHub (`gregkwoods/lapcounter-server-*`).

## Key Backend Files

- `api/app/main.py` - FastAPI app, all route definitions, DB engine setup
- `api/app/model.py` - SQLModel table definitions (drivers, cars, meetings, races, lanes, laps)
- `api/app/responsemodel.py` - Pydantic response models (`DriverWithLane`, `NextRaceSetup`)
- `api/app/next_race.py` - Lane assignment algorithm (core business logic, unit-tested independently)
- `api/app/settings.py` - Pydantic Settings (env vars from docker-compose)

## Key Frontend Files

- `react/src/components/LapCounter/LapCounter.jsx` - Main race UI (leaderboard, race controls)
- `react/src/components/NextRace/NextRace.jsx` - Driver-to-lane assignment UI
- `react/src/components/MqttSubscriber.jsx` - MQTT WebSocket connection
- `react/src/components/LapCounter/lapUtils.js` - Race logic helpers

## Lane Assignment Algorithm

`next_race.py:assign_drivers_to_lanes()` is the core business logic:
1. Sorts drivers by sit_out_next_race, then completed_races (fewest first), then random
2. Takes top N drivers where N = min(enabled lanes, available drivers)
3. Assigns each driver to the lane they've used least (fairness balancing)
4. Returns `NextRaceSetup` with `lane_assignments` (6 slots, some empty) and `other_drivers`

This function is deliberately DB-free for testability. The SQL query in `get_drivers_for_next_race_sql()` pre-sorts and aggregates lane counts.

## Database

PostgreSQL with SQLModel ORM (no relationships defined yet, uses raw SQL for complex queries).
- Dev credentials: user=`lap`, password=`lap`, db=`lapcounter_server`, port=5432
- Schema lives in `database/schema.sql`
- Key tables: `drivers`, `meetings`, `meeting_drivers`, `sessions`, `races`, `driver_races`, `driver_laps`, `lanes`, `cars`

## Environment Variables

Backend env vars are set in `compose.dev.yaml` and read via Pydantic Settings (`api/app/settings.py`).
React env vars use `VITE_` prefix and are compiled into the app at build time.

## Browser Target

The UI is optimized for 1920x1080 resolution with significant hardcoded CSS for that size.
