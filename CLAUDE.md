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
- **ble/** - Alternative Layer 1: reads laps from a Scalextric ARC Pro powerbase over Bluetooth LE instead of the two GPIO finish-line sensors, publishing the same `car_timestamp` contract. **Now the default Layer 1 on the live Pi** (`gpio` is the `--profile gpio` fallback), though still not validated against real hardware. See "Layer 1 hardware options" below for the protocol and future capabilities beyond lap timing.
- **lapdata/** - Hardware abstraction + race manager: normalises raw timing into `lap` events, tracks full race state, publishes `race_state`. `race_manager.py` is pure/DB-free and covered by `lapdata/test_race_manager.py` (see "Run Python tests" below). ⚠️ `last_crossing_time` must be set even on discarded first crossings (`count_first_crossing=False`) — without it, `race_time()` returns `0.0` and the initial position sort falls back to lane number order instead of crossing order; this is a regression test in that suite.
- **api/app/** - FastAPI backend (SQLModel ORM, PostgreSQL) — REST only, no race logic; see `api/CLAUDE.md` for endpoint/model docs
- **react/src/** - React 18 frontend — display only, subscribes to `race_state` via MQTT WebSocket, contains no race logic
- **dbwriter/** - Small service: subscribes to `driver_lap` (counted laps) and `race_state`. Writes `driver_laps` rows + `driver_races` aggregates **directly to PostgreSQL** (psycopg2, raw SQL — *not* via the API), and keeps `races`/`sessions` state in step with lapdata so persistence is browser-independent.

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
| `lap` | LapData | React (optional) | Raw normalised crossing — published for **every** crossing (incl. idle, non-running, and the discarded start-line crossing), with no race context. **Not** used for DB persistence. |
| `driver_lap` | LapData | DB Writer | Authoritative **counted** lap with full context — emitted only when the race manager actually counts a real lap. This is the DB-persistence contract. |
| `race_state` | LapData | React apps, DB Writer | Full computed state after every crossing (positions, lap counts, fastest laps) |
| `race_control` | Any client | LapData | Commands: `prepare`, `arm`, `start`, `status`, `pause`, `resume`, `end` |

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
`car` is 1-based lane number. `lapTime` filtered by `MINIMUM_LAP_TIME` env var. Published for every crossing — does **not** mean a lap was counted.

**`car_timestamp`:** `{"car":<1-6>,"timestamp":<unix_nanoseconds>,"lane":<1|2>}`

⚠️ **`timestamp` is when the crossing HAPPENED, and lapdata trusts it — it is not decorative.** Every Layer 1 stamps it at detection: GPIO in its interrupt callback, mocked-gpio at generation, BLE from the powerbase's own millisecond sensor clock. lapdata's `_crossing_ns()` uses that value for lap timing and for the `MINIMUM_LAP_TIME` phantom filter, rather than re-stamping on arrival, so MQTT and queueing latency stay out of lap times. It falls back to arrival time if the stamp is missing, non-numeric, or more than 30s from lapdata's own clock (`HW_TIMESTAMP_TOLERANCE_NS`) — a Layer 1 with a broken clock must not be able to poison race timing, which matters on a Pi with no RTC whose clock is set by hand before a meet.

This is why it matters for BLE specifically: the Slot characteristic is round-robin across all 6 cars, so a crossing is *reported* anywhere from ~0ms to a full cycle after it happened. Arrival time would fold that jitter into every lap — enough to make 3-decimal FastestLap rankings meaningless, and enough that a delayed notification could push two genuine crossings under `MINIMUM_LAP_TIME` and silently drop a real lap. A new Layer 1 **must** populate `timestamp` at detection time.

**`driver_lap`:** `{"race_id":<id>,"driver_id":<id>,"lane":<1-6>,"lap_number":<n>,"lap_time":<seconds>}`  
Emitted by lapdata only when `race_manager.on_lap` counts a real lap (so idle/non-running crossings and the discarded start-line crossing never produce one). The DB writer persists these verbatim — it re-derives no race logic.

**Discarded first crossing** is controlled by the **meeting**-level `meetings.count_first_crossing` flag (set in the Admin *meeting* form, not the session). It flows `meeting → /races/pending/ payload → lapdata load_lineup → race_manager.on_lap`: when false, each driver's first crossing is discarded (not counted, no `driver_lap`).

### Layer 1 hardware options: GPIO vs BLE

Three interchangeable Layer 1s all publish the same `car_timestamp` contract, so nothing above LapData cares which is running: `mocked-gpio` (software, default in `compose.dev.yaml`), `gpio` (two containers, one per physical GPIO sensor — Pi only), and `ble` (one container, talks to a Scalextric ARC Pro powerbase — see `ble/ble_to_timestamps.py`).

**Exactly one Layer 1 may run.** Two publishers on `car_timestamp` means every lap is counted twice, and at a meet that reads as a timing fault rather than a deploy fault. The defaults differ by environment, deliberately:

| | default Layer 1 | the other one |
|---|---|---|
| dev (`compose.dev.yaml`) | `mocked-gpio` | `ble` behind `--profile ble` |
| live Pi (`deploy/compose.race.yaml`) | `ble` | `gpio` behind `--profile gpio` |

`./deploy/deploy.ps1` takes `-Layer1 ble|gpio` (default `ble`) and both starts the right one and stops the other, then verifies exactly one is running. Two Compose behaviours make the manual path a trap, so prefer the script: a service that has been *profiled out* keeps **running** rather than being removed, and `ble` is unprofiled so even `--profile gpio up -d` starts it. Hence the stop must come **after** the `up`:
```
docker compose up -d && docker stop gpio-1 gpio-2          # -> ble
docker compose --profile gpio up -d && docker stop ble     # -> gpio
```
In dev the same trap exists in reverse: `mocked-gpio` is unprofiled, so a bare `docker compose --profile ble up` starts **both**. Stop `mocked-gpio` first, or name services explicitly.

⚠️ `ble` is the live default but has **not yet been validated against real powerbase hardware** — the first meet on it is the first real test. `-Layer1 gpio` is the fallback.

**BLE anchors the powerbase's clock to ours rather than using arrival time.** The Slot characteristic reports crossings in milliseconds since the powerbase's timer was last reset, which has no reporting jitter in it but is not a wall clock. `_device_to_wall()` converts it using a running **minimum** of `(arrival - device_time)`: every sample is the true offset plus some transport delay, delay is never negative, so the smallest sample seen is the best estimate and it converges within a few crossings. The anchor is thrown away and rebuilt whenever a device timestamp moves **backwards** (the powerbase zeroes its timers on Command 0/1) or on reconnect (it may have been power-cycled). A constant error in the anchor would cancel out of lap-to-lap deltas anyway; keeping it small also keeps lap 1 honest, since that one is timed from `race_start_time` rather than a previous crossing.

⚠️ **BLE crossings are edge-detected, so the first Slot packet per car after connecting only *seeds* the baseline — it never publishes.** The powerbase reports each car's last start/finish timestamp as absolute state, and keeps counting while nothing is connected (`POWER_ON_RACING` leaves the timers ticking; only commands 0 and 1 zero them). So on connect it hands over whatever each car's last crossing was. Comparing that against "unknown" would read as a change and fake a lap for **every** car — six phantom laps on a mid-race reconnect, straight into the leaderboard. Hence `_last_start_finish` distinguishes `[None, None]` ("not yet seeded since connecting") from `[0, 0]` ("seen, timers at zero"), and `handle_slot_notification()` returns early on the first packet. The accepted cost is missing a real crossing in the sub-second before a car's first round-robin packet. Don't "simplify" this back into a plain `!= previous` check.

The BLE protocol is Scalextric's official doc, obtained via customerservices.uk@scalextric.com, cross-checked against [RazManager/ScalextricArcBleProtocolExplorer](https://github.com/RazManager/ScalextricArcBleProtocolExplorer). A text copy is checked in at `ble/reference/Scalextric_ARC_BLE_Protocol.md`; the original `Scalextric_ARC_BLE_Protocol_live-1.docx` lives on Greg's machine under `OneDrive\Scalextric ARC Firmware, Protocols etc\`. `ble/` only implements the **Slot characteristic** (`0x3B0B`) for lap timing so far. The protocol exposes several other characteristics that GPIO structurally cannot — noted here so they aren't lost before BLE is adopted:

- **Throttle characteristic (`0x3B09`, notify, all 6 cars per packet, several times/sec)** — real-time throttle position (0–63) and brake/lane-change button state per car. This is the basis for a **simulated fuel consumption** feature: integrate `throttle × dt` continuously into a per-car running total (trivial computationally — 6 floats updated ~10–30×/sec). That integration belongs in the **BLE container** (it's the only place with access to raw throttle telemetry), published on its **own new topic** (e.g. `car_throttle`) — deliberately *not* folded into `car_timestamp`/`lap`, since fuel isn't a lap-boundary concept: a "low fuel" event has to be able to fire mid-lap, not only when a car happens to cross the start/finish line. So **LapData** would subscribe to `car_throttle` as a second, independent live input alongside `car_timestamp` (same "internal to LapData" treatment) and keep a continuously-decrementing `fuel_remaining` per driver, checking the low-fuel threshold on every throttle update rather than at lap boundaries. Crossing the threshold publishes its own event immediately, not gated on the next lap. One real consequence: `race_state` (or a fuel gauge within it) would then have two independent things driving updates — crossings *and* throttle ticks, which arrive far more often — so the publish cadence for fuel-driven state may need its own debounce rather than reusing "publish after every crossing" as-is. Since GPIO can never produce this data, it must stay optional, not a hard dependency.
- **Power multiplier + override flag** (Command characteristic `0x3B0A`, write) — software can cap or directly drive a car's power, independent of the physical controller. Could make a low-fuel/fuel-out state actually slow the car, not just display a number.
- **Throttle profile** (`0xFF01`–`0xFF06`, write, one per car) — a 64-entry throttle→power response curve per car. Could be reshaped as fuel drops (flatten the top end) for a "fuel-save mode."
- **Rumble** (per car, in `0x3B0A`) — haptic feedback in the physical hand controller, e.g. a low-fuel warning the driver feels.
- **KERS trigger** (per car, one bit in `0x3B0A`) — hardware already has a boost-button concept, if a "push to pass" mechanic is ever wanted.
- **Track characteristic (`0x3B0C`, notify)** — per-track overcurrent/undervoltage fault codes with a timestamp. Could surface as a "track fault" alert in race control instead of a silent power cutout.
- **CarID characteristic (`0x3B0D`, write)** — lets software assign a car's digital ID over BLE instead of the physical DIP-switch/programmer chip. Could simplify car setup in NextRace.

**BLE is now bidirectional for race lifecycle.** `ble/ble_to_timestamps.py` subscribes to `race_control` (same topic LapData subscribes to) and translates every command (`prepare`/`arm`/`start`/`pause`/`resume`/`end`) into a Command characteristic (`0x3B0A`) write of `POWER_ON_RACING`, both on each transition and once immediately on connect. This deliberately keeps Layer 1 dumb and behavior identical to GPIO (which has no ability to cut power at all) — lapdata's race manager remains the sole authority on which crossings count. Differentiating pause/end into other Command states (`POWER_ON_RACE_TRIGGER` for a yellow-flag-style halt that keeps power on, `POWER_ON_TIMER_HALT` to actually stop cars, or a future per-session "allow jump starts" toggle that holds power off between `arm` and `start`) is intentionally left for later — see `handle_race_control()`'s docstring. The paho (sync, own thread) → bleak (asyncio) handoff uses `asyncio.run_coroutine_threadsafe`, since bleak's client isn't safe to call directly from another thread; `_bleak_client`/`_ble_loop` are set once connected in `run()` and cleared on disconnect.

⚠️ **The Command payload's per-car power bytes are not padding.** Bytes 1–6 are the power *multiplier* (0…0x3f), and under `POWER_ON_RACING` the protocol doc says power output follows "the throttle levels **and** the car power bytes" — so sending zeros there caps every car at zero output and nothing moves, however hard the trigger is pulled. `_write_command_async()` sends `FULL_POWER` (0x3f) in bytes 1–6 for GPIO-parity pass-through; only bytes 7–19 (rumble/brake/KERS) are genuinely unused. The `0x80` bit (app drives the car directly, ignoring its controller) stays clear — that's what a future ghost-car or fuel-cut feature would set. `_write_command_async()` also swallows and logs its own exceptions: the Command write is optional garnish on top of this container's real job, and must never be able to tear down a working slot-notification subscription on a powerbase that rejects it (e.g. ARC One, which has no such characteristic).

BLE also subscribes to `race_state` and re-sends `POWER_ON_RACING` the instant it sees the transition into `Running` (`handle_race_state()`, tracking `_last_seen_race_state` to avoid rewriting on every crossing-triggered `race_state` publish). This matters because the actual lights-out "go" is an *internal* lapdata timer (`_do_lights_out()` in `timestamps_to_lapdata.py`) — it fires seconds after the `arm` race_control message and never publishes its own race_control command, so `race_state`'s `Running` transition is the only signal that lands exactly at go. The `arm`-time write and this one are deliberately redundant (belt-and-braces against e.g. a BLE reconnect mid-countdown).

**Refuel** is still an open question, not just plumbing: does it belong in BLE at all? Per the split above, **LapData** owns `fuel_remaining` (it's the one diffing/thresholding `car_throttle`), so a refuel action is naturally just LapData resetting its own in-memory value — no round-trip to BLE required, unless BLE ends up needing to know the fuel level itself (e.g. to drive rumble directly from hardware state rather than being told discrete commands). Recommended default: keep BLE dumb, handle refuel entirely inside LapData, and only route a message to BLE if a future feature (like rumble-on-low-fuel) needs BLE to *act* on it.

The throttle-driven features above it (fuel, power multiplier, throttle profiles, rumble, KERS, CarID) are still unimplemented — `ble/` only does lap timing plus the race-lifecycle Command writes described above, to keep parity with GPIO while that swap gets validated on real hardware first.

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
A root `pytest.ini` sets `testpaths = api/app, lapdata, ble`, so one command runs every
DB-free pure-logic suite (lane assignment, points scoring, the lapdata race manager,
crossing-timestamp handling, the BLE slot decoder and clock anchoring).

`ble/test_ble_to_timestamps.py` and `lapdata/test_timestamps.py` **stub `paho` and
`bleak` into `sys.modules` before importing** the module under test — neither is
installed in `api/.venv`, since those deps live in the containers' images. That works
because both modules keep their broker/BLE I/O behind `if __name__ == '__main__'`;
the containers still run them as `__main__`. Don't move that I/O back above the guard.

Only the `api/.venv` has pytest installed, so invoke it explicitly:
```powershell
./api/.venv/Scripts/python.exe -m pytest
```
Run one file or one test:
```powershell
./api/.venv/Scripts/python.exe -m pytest lapdata/test_race_manager.py
./api/.venv/Scripts/python.exe -m pytest api/app/test_next_race.py::test_lane_preference
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

React publishes `race_control` directly to MQTT (not via API) for speed and so non-browser clients work the same way. **It no longer persists race state** — that is owned by lapdata server-side (see below), so the display is a pure viewer and persistence works with no browser open.

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
- Key tables: `drivers`, `meetings`, `meeting_drivers`, `sessions`, `races`, `driver_races`, `driver_laps`, `lanes`, `cars`, `race_withdrawals`, `session_drivers`

### Rebuild the database
```
docker exec -i database psql -U lap -d lapcounter_server < database/schema.sql
docker exec -i database psql -U lap -d lapcounter_server < database/sampledata.sql
```
Alternatively, run `python sampledata.py` inside the `api` container (drops all tables, recreates, seeds).

### Upgrading a database that holds real data

Both rebuild paths above **DROP everything**, so neither is how you add a column to the
race Pi's live meeting data. Numbered, re-runnable scripts in `database/migrations/` do
that instead:
```
docker exec -i database psql -U lap -d lapcounter_server < database/migrations/001-races-started-at.sql
```
Add one whenever `model.py` gains a column, and keep `schema.sql` in step for fresh
builds. This matters more than it looks: SQLModel names every mapped column explicitly in
its SELECTs, so one missing column takes out *all* of that table's endpoints with
`UndefinedColumn` — not just the feature that added it.

### Key schema notes
- `meeting_cars.lane` — nullable INT, unique per `(meeting_id, lane)`. Source of truth for car-to-lane assignment when building a race lineup.
- `driver_races` stores both `car_id` and `lane` independently — they can diverge if a car is swapped mid-meeting. `lane` drives the fairness algorithm; `car_id` is the historical record.
- `lanes` is a static lookup table (lane_number 1–6, color, enabled flag). Not a physical constraint.
- `RaceSession` model maps to the `sessions` table (should eventually be renamed `race_sessions`).
- **A session owns an ordered queue of `NotStarted` races.** The whole session is pre-populated when it starts (`POST /sessions/start-next`) so every active driver is scheduled for exactly `races_per_driver` balanced races. The earliest queued race (by `race_number`) is the *next/current* race; the rest are the lookahead the NextRace page previews. (This replaces the old "at most one `NotStarted` race" rule.) Reads never create races; generation happens only on `start-next` and `regenerate-races`. A `NotStarted` race never outlives a `Finished` session — `finish_session` / auto-end delete the queue.
- `MeetingDriver.driver_name` is the computed display name (usually `first_name`, but includes last initial when two drivers share a first name). Always use `driver_name` in the UI, not `Driver.first_name`.
- **`DriverRace.fastest_lap_time` and `laps_completed` are defined in the model but never populated by any current code path.** For per-driver lap time analysis, always use `DriverLap` records joined through `driver_race_id`. `build_session_results()` already does this for FastestLap sessions.
- `race_withdrawals` `(race_id, driver_id)` — one row per operator removal (NextRace ×). Deleted when the driver is re-added or when a `NotStarted` race is discarded (`remove_pending_races`), so only withdrawals on `Finished` races count as skips. **Schema drop order:** it (and `session_drivers`) must be dropped **before** `races`/`sessions`/`drivers` in `schema.sql` or the `DROP TABLE`s fail on the FK dependency.
- `session_drivers` `(session_id, driver_id, disqualified)` — per-session, per-driver state; currently just the `disqualified` flag. See "Sit-out tracking & disqualification".
- `races.started_at` — the lights-out ("go go go") instant, nullable. Race timing has always been derived from this moment, not the first car crossing (`race_manager.py`'s `start()` sets `race_start_time`; lap 1 is timed from it) — this column just persists what lapdata already computed. Set via `POST /races/{race_id}/start`'s optional `started_at` body field, which lapdata populates from `race.race_start_time` (a precise in-process timestamp) rather than letting the API stamp its own `NOW()`, since that POST is fire-and-forget from a background thread and would be measurably later than the real go instant.

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
- **Race queue (fetch decoupled from generate):**
  - `GET /races/pending/` — **read-only**: the next race to run (head of the session's queue), or `404` if none. Never creates.
  - `GET /races/current/` — **read-only**: the Running race, else the queue head, else `404`.
  - `GET /races/queue/` — **read-only**: the ordered upcoming (`NotStarted`) races for the active session — the NextRace lookahead.
  - `POST /sessions/start-next` — **"Next Session"**: promotes the next `NotStarted` session → `InProgress` and pre-populates its **whole** balanced race queue (`build_session_schedule()` iterates `select_balanced_race_drivers()` + `assign_drivers_to_lanes()` over in-memory copies). `409` if a session is already in progress, `404` if none queued. *This is the only thing that creates a session's races — no race exists until its session is started.*
  - `POST /sessions/{id}/regenerate-races` — rebuild the upcoming queue from each driver's **outstanding** race count (finished/running races untouched). For late arrivals: a roster change leaves an eligible driver out of the queue, which `GET /sessions/active/regen-status` reports so RaceControl shows a *"New driver added, regenerate upcoming races?"* prompt. Operator-triggered.
- `POST /races/{id}/start` — sets race Running, promotes session to InProgress if still NotStarted; **POSTed server-side by lapdata** in `publish_race_state()` on the `Running` transition (browser-independent). Starting a race is the manual `/racecontrol` action that promotes its session.
- `POST /races/{id}/finish` — sets race Finished; for sessions with a `races_per_driver` target it **auto-ends** the session when every active driver has reached the target. **Does NOT start the next session** — that is a manual `/racecontrol` action (start the first race of the next session). POSTed server-side by lapdata on the `Finished` transition.

> **Lifecycle pattern: ending is automatic, starting is manual.** A race ends automatically (target laps / time expiry); the operator manually advances through the queue (`/racecontrol`: Next Race → Start Race). A session ends automatically (every driver reached `races_per_driver`); the operator starts the next session with **Next Session** (`POST /sessions/start-next`), which promotes it and pre-populates its queue. Between a session ending and the next being started there is deliberately *no* current/pending race. lapdata owns the *automatic* side (it POSTs start/finish to the API on transitions); `/racecontrol` owns the *manual* side.
- `POST /sessions/{id}/finish` — ends a session (does **not** promote the next — that's the manual Next Session step) and deletes the session's `NotStarted` queue
- `PATCH /lanes/{lane_number}` — enable/disable a lane, updates pending race lineup
- Lane assignment algorithm (`next_race.py`) with 8 pytest unit tests
- **Session model is two independent axes** (`end_condition` is per-*race*, `races_per_driver` is per-*session*; they coexist — previously they were mutually exclusive):
  - **Per-race end** — `end_condition` / `end_condition_info`: `'Laps'` + lap count for Finishing Position races, `'Time'` + minutes for Fastest Lap races. Derived from race type in the Admin form, not chosen directly.
  - **Automatic session end** — `races_per_driver` (nullable INT; `None` = manual end only). When set, the session ends once every active driver has raced that many times.
  - **Sit-out limit** — `max_sit_outs` (nullable INT; `None` = no limit). How many times a driver may be pulled from a race before RaceControl offers to disqualify them from the rest of the session (see "Sit-out tracking & disqualification" below).
- **Balanced session-end scheduling** (`select_balanced_race_drivers()` in `next_race.py`): picks one race's drivers so the session finishes with **every driver having raced exactly `races_per_driver` times, with no tiny final race**. It spreads remaining driver-slots over the fewest races (`ceil(slots / lanes)`) and shrinks later races evenly — e.g. 7 drivers / 6 lanes / target 3 ⇒ race sizes 6,5,5,5 (not 6,6,6,3). Drivers are taken fewest-raced-first (SQL pre-sorts). `build_session_schedule()` iterates this over in-memory driver copies (incrementing each chosen driver's `completed_races`/lane counts) to pre-generate the **whole** session queue at once; `compute_session_progress()` projects `session_races_done` / `session_races_total` for the "Race X of Y" title.
- **Sit-out tracking & disqualification** — resolves the ambiguity of the NextRace **×** (remove-driver) button. A bare × means *out of this race only*: the driver keeps their `races_per_driver` target, so the balancer schedules make-up races and later races legitimately run **short** (this is correct-by-design, not a bug — it's how the session stays balanced while a possibly-returning driver is still owed races). To bound this, each × records a **withdrawal** (`race_withdrawals` table, keyed by `(race_id, driver_id)`); a withdrawal becomes a **skip** only once its race actually **finishes** (`session_skip_counts()` counts withdrawals on the session's `Finished` races — effectively "counted at finish time"). **Rotation never counts** — a driver the scheduler simply didn't include this race leaves no withdrawal; only an explicit operator removal does. Skips are **cumulative** across the session. When a driver's skips reach the per-session **`max_sit_outs`** limit (nullable INT; `None` = no limit), `GET /sessions/active/regen-status` returns them in `sit_out_candidates` and RaceControl shows a **disqualify prompt**. `POST /sessions/{id}/drivers/{driver_id}/disqualify` sets the per-session `session_drivers.disqualified` flag and regenerates the queue so remaining races refill without them; a disqualified driver is excluded from **every** scheduling path (`assign_drivers_to_lanes`, `select_balanced_race_drivers`, `compute_session_progress`, `set_lane_enabled`, the `finish_race` auto-end check) via a `disqualified` field on `DriverWithLane` that `get_drivers_for_next_race_sql` populates from a LEFT JOIN. **`disqualified` is per-session**, distinct from the global one-race `Driver.sit_out_next_race`. `POST /sessions/{id}/drivers/{driver_id}/reinstate` (and re-adding the driver in NextRace) clears the flag **and** their withdrawals (`clear_session_withdrawals()`) so a deliberate return forgives past sit-outs and the prompt doesn't immediately re-fire.
- `FastestLap` session type: ranking is always personal best (the old "Ranking" dropdown and `AverageFastestLap`/`LapPoints` options were removed; `scoring_method` is now always `'PositionPoints'` for Finishing Position and `'FastestLap'` for Fastest Lap). Results computed from `DriverLap` records in `build_session_results()`, sorted ascending; Results page shows `FastestLapResultsTable`.
- Admin session form is simplified: **Race Type** (Finishing Position / Fastest Lap), **Race Laps** *or* **Race Time (min)**, **Points scoring** (Finishing Position only), **Session ends after N races per driver**, and **Disqualify after N sit-outs** (blank = no limit → `max_sit_outs`). No End Condition / Scoring method / Ranking / Start+End time fields.
- Admin meetings list: meetings are collapsed except the in-progress one (or the latest if none is in progress); "In Progress" is a non-clickable badge after the session type; an **End Session** button on the right opens a confirmation modal → `POST /sessions/{id}/finish`.
- Results page lap times: no `s` suffix, regular weight, figure-space-padded (`fmtLap`) so single- and double-digit seconds align.
- React Router with `/` (LapCounter) and `/nextrace` (NextRace) routes
- NextRace UI: lane toggle, × remove driver, + add driver from bench, car image selector all live

**In progress — LapData race manager refactor:**
- LapData to own all race state (positions, lap counts, fastest laps, race end)
- LapData to publish `race_state` MQTT topic after every lap crossing
- React to subscribe to `race_state` and delete all race logic (`lapUtils.js`)
- ✅ DB Writer service implemented (`dbwriter/`) — subscribes to `driver_lap` + `race_state`, writes `driver_laps`/`driver_races` straight to PostgreSQL
- ✅ `race_control` MQTT topic for race prepare/arm/start/pause/resume/end/status from any client (used by the `/racecontrol` page)

**Still needed:**
- Meeting and session creation UI (Admin page currently only lists existing meetings/sessions)
- NextRace page: preview the full upcoming queue (`GET /races/queue/`) and edit specific queued races; currently it edits only the head race
- Sample/reset data pre-populates only finished races — the pending **queue** must be generated by starting the session (`start-next`) or, for the pre-seeded InProgress session 2, by `POST /sessions/2/regenerate-races` (RaceControl's regenerate prompt does this). Folding queue generation into `reset-races.sql`/`sampledata.py` is still TODO.

Note: `GET /drivers/nextrace/` (old stateless endpoint) still exists alongside `GET /races/pending/`. The old one is superseded but not yet removed.
