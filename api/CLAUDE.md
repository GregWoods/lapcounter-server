# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in the `api/` directory.

## Overview

FastAPI backend for the Scalextric lap counter system. Serves REST endpoints for race management: drivers, cars, meetings, sessions, races, and lane assignments. Connects to PostgreSQL via SQLModel ORM.

## Running

### Via Docker (preferred)
```
docker compose -f ../compose.dev.yaml up --build api
```
This starts the API with auto-reload on port 8000. Requires the `database` service to be running too — usually start the full stack with `docker compose -f ../compose.dev.yaml up --build`.

### Without Docker
```powershell
# Set env vars (required — Pydantic Settings will fail without them)
. ./setenv.ps1

# Activate venv and run
./.venv/Scripts/activate
cd app
fastapi dev main.py
```
Requires a PostgreSQL instance running on localhost:5432 (the Docker `database` container, or a local install).

### Swagger UI
http://localhost:8000/docs — auto-generated from FastAPI route definitions.

## Tests

A root `pytest.ini` (repo root) runs this directory alongside `lapdata/`'s tests in one
invocation — see the top-level CLAUDE.md "Run Python tests". From here directly:
```
python -m pytest api/app
```
Single test:
```
python -m pytest api/app/test_next_race.py::test_lane_preference
```

`test_next_race.py` covers `assign_drivers_to_lanes()` — the pure-logic function with no
DB dependency, using fixtures for `Lane` and `DriverWithLane` objects. `test_points.py`
covers `PositionPoints` scoring.

## File Structure

```
api/
├── app/
│   ├── main.py           # FastAPI app: routes, DB engine, session DI, CORS, exception handler
│   ├── model.py          # SQLModel table definitions (15 models)
│   ├── responsemodel.py  # Response-only models: DriverWithLane, NextRaceSetup
│   ├── next_race.py      # Lane assignment algorithm + SQL query for driver data
│   ├── settings.py       # Pydantic Settings (reads env vars)
│   ├── sampledata.py     # Drop/create tables + seed sample data script
│   ├── test_next_race.py # pytest tests for assign_drivers_to_lanes()
│   ├── requirements.txt  # Pinned dependencies (installed in Docker build)
│   └── media/cars/       # Car images served as static files at /media/cars/
├── Dockerfile.dev        # Dev image: `fastapi dev` with hot reload
├── Dockerfile.prod       # Prod image: `fastapi run`
├── setenv.ps1            # PowerShell env vars for running outside Docker
└── README.md
```

## Environment Variables

All required — set by `compose.dev.yaml` in Docker, or `setenv.ps1` locally. Read via Pydantic Settings in `settings.py`:

| Variable | Dev value | Purpose |
|---|---|---|
| `API_URL` | `http://localhost:8000` | Base URL for constructing car image URLs |
| `REACT_URL` | `http://localhost:8088` | CORS allowed origin |
| `MEDIA_FOLDER` | `media` | Static files mount point |
| `CARS_MEDIA_FOLDER` | `media/cars` | Car images subfolder |
| `DB_DATABASE` | `lapcounter_server` | PostgreSQL database name |
| `DB_HOST` | `database` (Docker) / `localhost` | PostgreSQL host |
| `DB_USER` | `lap` | PostgreSQL user |
| `DB_PASSWORD` | `lap` | PostgreSQL password |
| `DB_PORT` | `5432` | PostgreSQL port |

## Database Models (`model.py`)

All models use SQLModel (SQLAlchemy + Pydantic). No SQLModel relationships are defined — joins use raw SQL where needed.

**Core race management:**
- `Meeting` — a race event (name, date, venue)
- `RaceSession` — a session within a meeting. Two independent end axes: `end_condition` (per-race: `Laps` for Finishing Position, `Time` for Fastest Lap) + `end_condition_info`, and `races_per_driver` (per-session automatic end; nullable, `None` = manual end). `scoring_method` is `PositionPoints` (Finishing Position) or `FastestLap` (personal best)
- `Race` — individual race (state: NotStarted/Running/Finished)
- `DriverRace` — links a driver + car + lane for one race (unique constraint on driver_id + race_id)
- `DriverLap` — individual lap time record

**People & vehicles:**
- `Driver` — racer (first_name, last_name, sit_out_next_race flag)
- `Car` — vehicle with foreign keys to CarModel, CarTyre, ChipHardware, ChipFirmware
- `CarModel`, `CarManufacturer`, `CarCategory` — vehicle classification hierarchy
- `CarTyre`, `ChipHardware`, `ChipFirmware` — lookup tables

**Junction tables:**
- `MeetingDriver` — links driver to meeting, stores `driver_name` (computed display name, usually first_name but includes last initial for disambiguation)
- `MeetingCar` — links car to meeting

**Track:**
- `Lane` — lanes 1-6 (color, enabled flag). Primary key is `lane_number`.

## API Endpoints (`main.py`)

**Meetings:**
- `GET /meetings` — all meetings
- `GET /meetings/upcoming` — meetings with date >= now

**Sessions:**
- `GET /sessions?meeting_id=N` — all sessions, optionally filtered by meeting

**Drivers:**
- `GET /drivers/` — paginated list (offset/limit)
- `GET /drivers/{id}` — single driver
- `POST /drivers/` — create driver
- `DELETE /drivers/{id}` — delete driver
- `GET /drivers/nextrace/` — calculates lane assignments for the next race

**Other:**
- `GET /api/cars` — list car image URLs from the filesystem
- `GET /verify-db`, `/import-check`, `/minimal-debug`, `/meetings-schema` — diagnostic endpoints

All DB-accessing endpoints use `SessionDep` (FastAPI dependency injection via `Annotated[Session, Depends(get_session)]`).

## Lane Assignment Algorithm (`next_race.py`)

Two functions:

### `get_drivers_for_next_race_sql(session)`
Raw SQL query that aggregates per-driver stats:
- Joins `drivers` → `meeting_drivers` → `driver_races` → `races` (only Finished races)
- Counts total completed races and per-lane counts (lane1_count through lane6_count)
- Adds `RANDOM()` column for tie-breaking
- Orders by: sit_out_next_race ASC, completed_races ASC, random ASC
- Returns list of `DriverWithLane` objects

### `assign_drivers_to_lanes(driver_list, lanes)`
Pure logic function (no DB, fully unit-testable):
1. Re-sorts drivers by (sit_out_next_race, completed_races, random_value) — needed for unit tests which don't go through SQL
2. Filters out drivers with `sit_out_next_race=True`
3. Takes top N available drivers where N = min(enabled lanes, available drivers)
4. Shuffles lane slots randomly, then assigns each driver to the lane they've used least (`lane{N}_count` attribute)
5. Re-sorts by lane number
6. Returns `NextRaceSetup(lane_assignments=[6 slots], other_drivers=[remaining])`

Empty lanes get a blank `DriverWithLane` with `id=0`.

## Response Models (`responsemodel.py`)

### `DriverWithLane`
Flat model combining driver stats with lane info. Not a DB table — used only for API responses and internal logic. Key fields: `id`, `driver_name`, `completed_races`, `sit_out_next_race`, `lane1_count`..`lane6_count`, `random_value`, `lane_number`, `lane_color`, `lane_enabled`.

Factory methods:
- `DriverWithLane.create(driver=..., lane=...)` — compose from a driver and/or lane
- `add_driver_to_lane(driver)` — copy driver attrs into an existing lane slot

### `NextRaceSetup`
- `lane_assignments: list[DriverWithLane]` — always 6 entries (one per lane), some may be blank
- `other_drivers: list[DriverWithLane]` — drivers not racing, sorted by completed_races

## Seeding Data (`sampledata.py`)

Run directly to drop all tables, recreate them from SQLModel metadata, and insert sample data:
```
python sampledata.py
```
Requires env vars to be set (use `setenv.ps1` or run inside Docker container). Inserts data in FK dependency order: manufacturers → categories → models → tyres → chips → cars → drivers → meetings → junction tables → sessions → races → driver_races → driver_laps → lanes.

## Docker

- **Dev** (`Dockerfile.dev`): Python 3.12.8-bookworm, `fastapi dev` with hot reload. The `app/` directory is bind-mounted from compose so edits are reflected immediately.
- **Prod** (`Dockerfile.prod`): Same base, `fastapi run` (production Uvicorn).

## Patterns & Conventions

- CORS allows `REACT_URL`, `localhost:5173` (local Vite), and `localhost:8088` (Docker Vite)
- Global exception handler catches unhandled exceptions and returns full tracebacks in JSON (dev-friendly, not production-safe)
- `model.py` uses `from model import *` in `main.py` and `next_race.py` — all table classes are in the global namespace
- Table names are pluralized (`drivers`, `meetings`, `cars`, etc.)
- `RaceSession` model maps to table `sessions` (comment notes it should be renamed to `race_sessions`)
