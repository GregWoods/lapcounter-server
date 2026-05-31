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
- **api/app/** - FastAPI backend (SQLModel ORM, PostgreSQL); see `api/CLAUDE.md` for detailed API docs
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

### Run API without Docker
```powershell
. ./api/setenv.ps1
cd api && ./.venv/Scripts/activate
cd app && fastapi dev main.py
```
Requires PostgreSQL running on localhost:5432 (the Docker `database` container works).

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
- `api/app/model.py` - SQLModel table definitions (15 models)
- `api/app/responsemodel.py` - Pydantic response models (`DriverWithLane`, `NextRaceSetup`)
- `api/app/next_race.py` - Lane assignment algorithm + helpers for pending race persistence
- `api/app/settings.py` - Pydantic Settings (env vars from docker-compose)
- `api/app/sampledata.py` - Script to drop/recreate all tables and seed sample data (run directly inside the container)

## Key Frontend Files

- `react/src/components/LapCounter/LapCounter.jsx` - Main race UI (leaderboard, race controls)
- `react/src/components/NextRace/NextRace.jsx` - Driver-to-lane assignment UI
- `react/src/components/MqttSubscriber.jsx` - MQTT WebSocket connection
- `react/src/components/LapCounter/lapUtils.js` - Race logic helpers (modifyDriversViewModel, calculateLapTime, checkEndOfRace)
- `react/src/defaultConfig.js` - Shared config, race defaults, and driver factory functions

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
- Schema lives in `database/schema.sql` — kept in sync with `api/app/model.py`
- Sample data in `database/sampledata.sql`
- Key tables: `drivers`, `meetings`, `meeting_drivers`, `sessions`, `races`, `driver_races`, `driver_laps`, `lanes`, `cars`

### Rebuild the database
```
docker exec -i database psql -U lap -d lapcounter_server < database/schema.sql
docker exec -i database psql -U lap -d lapcounter_server < database/sampledata.sql
```
Alternatively, run `python sampledata.py` inside the `api` container (drops all tables, recreates, seeds).

### Key schema notes
- `meeting_cars.lane` — nullable INT, unique per `(meeting_id, lane)`. Source of truth for car-to-lane assignment when building a race lineup.
- `driver_races` stores both `car_id` and `lane` independently — they can diverge if a car is swapped mid-meeting. `lane` drives the fairness algorithm; `car_id` is the historical record.
- `lanes` is a static lookup table (lane_number 1–6, color, enabled flag). Not a physical constraint.
- `RaceSession` model maps to the `sessions` table (should eventually be renamed `race_sessions`).
- At most one `Race` with `state='NotStarted'` at a time — this is the "pending race".

## Environment Variables

Backend env vars are set in `compose.dev.yaml` and read via Pydantic Settings (`api/app/settings.py`).
React env vars use `VITE_` prefix and are compiled into the app at build time.
For local (non-Docker) API development, `api/setenv.ps1` sets all required vars.

## Browser Target

The UI is optimized for 1920x1080 resolution with significant hardcoded CSS for that size.

## Branch: `race_meet_manager` (WIP) vs `main`

The `main` branch is a working lap counter with no database. The `race_meet_manager` branch adds race meet management — the ability to persist drivers, cars, meetings, and race history across sessions.

The active implementation plan is in `INTEGRATION_PLAN.md` — read this before making changes to the API/React integration. It describes 5 phases for connecting the NextRace UI to the LapCounter via a "pending race" concept.

### Current implementation status (race_meet_manager)

**Completed:**
- PostgreSQL + SQLModel ORM: 15 table models in `api/app/model.py`
- Full driver CRUD, meetings, sessions endpoints
- `GET /races/pending/` — loads or creates a pending race (used by both `/nextrace` and `/` routes)
- `POST /races/{id}/start` and `POST /races/{id}/finish` — race state transitions
- Lane assignment algorithm (`next_race.py`) with 8 pytest unit tests
- React Router with `/` (LapCounter) and `/nextrace` (NextRace) routes; `/nextrace` loads from `/races/pending/`
- NextRace UI showing lane assignments (color-coded) and other drivers

**Remaining (see INTEGRATION_PLAN.md for details):**
- Phase 2: Wire up the × and + edit buttons in NextRace.jsx (`PUT /races/pending/lineup`)
- Phase 3: LapCounter loads driver names from pending race (add loader to `"/"` route in `router.jsx`)
- Phase 4 (partial): `POST /races/{id}/laps` for writing lap events to DB
- Phase 5: "Load Next Race" button after a race finishes
