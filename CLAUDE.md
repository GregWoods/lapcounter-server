# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scalextric digital lap counter and race management system. A 4-layer Docker-based architecture running on Raspberry Pi that counts laps, manages races, and serves a real-time leaderboard via web browser. Designed to work fully offline (Pi acts as WiFi AP).

## Architecture

```
GPIO / BLE / future hardware (Layer 1)
        ↓ car_timestamp
LapData — hardware abstraction + race manager (Layer 2)
        ↓ lap          ↓ race_state       ↑ race_control
DB Writer service    React apps        Any client
        ↓               (display only)  (browser, button box, app)
   PostgreSQL ← API (REST, queries + lineup management)
```

- **mosquitto/** - Eclipse Mosquitto MQTT broker config
- **gpio/** - Raspberry Pi GPIO reader (has `Dockerfile.Mocked` for dev without hardware)
- **lapdata/** - Hardware abstraction + race manager: normalises raw timing into `lap` events, tracks full race state, publishes `race_state`
- **api/app/** - FastAPI backend (SQLModel ORM, PostgreSQL) — REST only, no race logic; see `api/CLAUDE.md` for endpoint/model docs
- **react/src/** - React 18 frontend — display only, subscribes to `race_state` via MQTT WebSocket, contains no race logic
- **dbwriter/** *(planned)* - Small service: subscribes to `lap`, persists to DB via API

### Core design principles

- **Queries are HTTP, events are MQTT.** The API answers "what is the pending race?" React POSTs race control signals to the API for DB side-effects, but the live signal goes via MQTT.
- **`car_timestamp` is internal to LapData.** Nothing else subscribes to it. It is the hardware-specific interface; everything above depends on `lap` only.
- **`lap` is the stable contract** — the seam between hardware and software. Changing hardware (GPIO → BLE) only requires a new Layer 1 that publishes the same `car_timestamp` format.
- **Race state is browser-independent.** LapData holds race state in memory; React is a viewer that can reconnect at any time and immediately receive current state.
- **Any client can publish `race_control`** — browser, physical button box, mobile app. LapData doesn't care who sent it.

### MQTT Topics

| Topic | Publisher | Subscribers | Description |
|---|---|---|---|
| `car_timestamp` | GPIO/Layer 1 | LapData only | Raw hardware event — internal, do not subscribe elsewhere |
| `lap` | LapData | DB Writer, React (optional) | Normalised lap crossing — the stable public interface |
| `race_state` | LapData | React apps | Full computed state after every crossing (positions, lap counts, fastest laps) |
| `race_control` | Any client | LapData | Commands: `start`, `pause`, `resume`, `end` |

**`race_control`:** `{"command": "start", "race_id": 5}`

**`race_state`:**
```json
{
  "race_id": 5, "state": "Running", "target_laps": 20,
  "race_fastest_lap": 4.523, "race_start_time": 1749123456.789,
  "drivers": [
    { "lane": 1, "driver_id": 9, "driver_name": "Jake",
      "laps_completed": 3, "laps_remaining": 17,
      "last_lap": 5.123, "best_lap": 4.987, "total_race_time": 15.234,
      "position": 1, "finished": false, "suspended": false, "has_started": true }
  ]
}
```

**`lap`:** `{"type":"lap","car":<1-6>,"time":<unix_seconds>,"lapTime":<elapsed_seconds>}`  
`car` is 1-based lane number. `lapTime` filtered by `MINIMUM_LAP_TIME` env var.

## Development Commands

### Start full stack (Docker)
```
docker compose -f compose.dev.yaml up --build
```
- React: http://localhost:8088 (hot module reloading)
- API: http://localhost:8000 (auto-reload via uvicorn)
- API docs (Swagger): http://localhost:8000/docs
- PgAdmin: http://localhost:5050

> **⚠️ `lapdata` does NOT hot-reload.** React (Vite HMR) and the API (`uvicorn --reload`)
> pick up source edits live, but `lapdata` runs a plain `python … loop_forever()`. Even
> though `./lapdata` is volume-mounted, the running process keeps the *old* code until you
> restart it. After editing anything under `lapdata/` (e.g. `race_manager.py`):
> ```
> docker compose -f compose.dev.yaml restart lapdata
> ```
> When debugging race logic, **verify against the running system, not just the source** —
> a stale `lapdata` process will make correct fixes look like they "made no difference".
> Drive it directly with the MQTT clients inside the `mosquitto` container:
> ```
> docker exec mosquitto mosquitto_pub -t race_control -m '{"command":"start","race_id":24,"target_laps":20}'
> docker exec mosquitto mosquitto_sub -t race_state -C 5 -W 15   # capture 5 messages, 15s timeout
> ```
> (`docker logs lapdata --tail 20` shows the lap/race-state activity. Use single quotes for
> the JSON payload and separate `docker exec` calls — nested-quote escaping breaks otherwise.)

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
- `react/src/components/LapCounter/lapUtils.js` - Race logic helpers — **being phased out** as race logic moves to LapData
- `react/src/defaultConfig.js` - Shared config, race defaults, and driver factory functions
- `react/src/router.jsx` - React Router Data Mode (`createBrowserRouter` with `loader` functions — data is fetched before render)

### React is display-only (target state)

React subscribes to `race_state` via MQTT and renders it. It contains no race logic. `lapUtils.js` (`calculateLapTime`, `modifyDriversViewModel`, `checkEndOfRace`) is being deleted as part of the LapData race manager refactor.

React publishes `race_control` directly to MQTT (not via API) for speed and so non-browser clients work the same way. It also fires `POST /races/{id}/start` to the API as fire-and-forget for DB state.

Planned routes: `/` (leaderboard), `/nextrace` (lineup), `/tv` (full-screen display), `/driver/N` (per-driver view).

### Current React State Architecture (transitional)

`drivers[]` and `lapData[]` are parallel arrays, both indexed **0–5 by lane number** (not by position). `drivers[0]` is always lane 1. Visual position sorting is done via CSS `order` — the array is always re-sorted by `driver.number` at the end of `modifyDriversViewModel`. This will be replaced by rendering `race_state.drivers` directly from MQTT.

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
- `MeetingDriver.driver_name` is the computed display name (usually `first_name`, but includes last initial when two drivers share a first name). Always use `driver_name` in the UI, not `Driver.first_name`.

## Environment Variables

Backend env vars are set in `compose.dev.yaml` and read via Pydantic Settings (`api/app/settings.py`).
React env vars use `VITE_` prefix and are compiled into the app at build time.
For local (non-Docker) API development, `api/setenv.ps1` sets all required vars.

## Browser Target

The UI is optimized for 1920x1080 resolution with significant hardcoded CSS for that size.

## Branch: `race_meet_manager` (WIP) vs `main`

The `main` branch is a working lap counter with no database. The `race_meet_manager` branch adds race meet management and is being refactored toward the MQTT-centric architecture above.

### Current implementation status

**Completed:**
- PostgreSQL + SQLModel ORM: 15 table models in `api/app/model.py`
- Full driver CRUD, meetings, sessions endpoints
- `GET /races/pending/` — loads or creates a pending race
- `POST /races/{id}/start` and `POST /races/{id}/finish` — race state transitions
- `PATCH /lanes/{lane_number}` — enable/disable a lane, updates pending race lineup
- Lane assignment algorithm (`next_race.py`) with 8 pytest unit tests
- React Router with `/` (LapCounter) and `/nextrace` (NextRace) routes
- NextRace UI: lane toggle (enable/disable) is live; `/` route loads driver names from pending race on page load

**In progress — LapData race manager refactor:**
- LapData to own all race state (positions, lap counts, fastest laps, race end)
- LapData to publish `race_state` MQTT topic after every lap crossing
- React to subscribe to `race_state` and delete all race logic (`lapUtils.js`)
- New DB Writer service to subscribe to `lap` and persist to DB
- `race_control` MQTT topic for race start/pause/end from any client

**Still needed (NextRace UI):**
- × and + edit buttons to swap specific drivers in/out of lanes (`PUT /races/pending/lineup`)
- "Load Next Race" button in LapCounter after a race finishes

Note: `GET /drivers/nextrace/` (old stateless endpoint) still exists alongside `GET /races/pending/`. The old one is superseded but not yet removed.
