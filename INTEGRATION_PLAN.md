# Plan: Connect LapCounter UI to NextRace Database

## Context

Currently the two UIs are islands. The NextRace page (`/nextrace`) calculates a fair driver-to-lane assignment from the database, but LapCounter (`/`) knows nothing about it — it stores drivers only in `localStorage` with hardcoded default names. Race results (laps, times, positions) are never written back to the DB, so the lane-assignment algorithm has no real data to work with.

The goal is to close this loop: NextRace persists its lineup, LapCounter loads and races it, results are written back, and after the race the user can trigger the next lineup.

---

## Architecture: "Pending Race" Concept

A **pending race** is a `Race` record with `state='NotStarted'` plus its `DriverRace` records (one per lane). This lives in the DB between when NextRace is viewed and when the race finishes.

1. **NextRace loads** — check DB for a `NotStarted` race; if none, calculate assignment and save it as a new `Race` + `DriverRace` records
2. **NextRace editing** — user swaps/removes/adds drivers; changes written to the pending `DriverRace` records via `PUT /races/pending/lineup`
3. **LapCounter loads** — fetches the pending race via `GET /races/pending/` (same endpoint as step 1); initialises driver names and lane numbers from the saved assignment
4. **Race runs** — MQTT lap events are processed locally as today, and also POSTed to `POST /races/{id}/laps`
5. **Race finishes** — `POST /races/{id}/finish` marks the `Race` as `Finished`; `DriverRace` records updated with final lap counts
6. **Load next race** — user clicks "Load Next Race" in LapCounter; `GET /races/pending/` is called, which finds no `NotStarted` race, calculates and saves a fresh lineup, and returns it to reinitialise LapCounter

---

## Database

Schema changes already made (in `database/schema.sql` and `api/app/model.py`):
- `lanes` table added (lane_number 1–6, color, enabled)
- `meeting_cars.lane` added — nullable `INT` with `UNIQUE(meeting_id, lane)`. Records which lane each car runs in for a given meeting. This is the source of truth for car-to-lane assignment when building a race lineup.
- `driver_races.lane`, `laps_completed`, `last_lap_time`, `fastest_lap_time` added
- `drivers.sit_out_next_race` added
- `driver_races` keeps both `car_id` and `lane` independently — they can diverge if a car is swapped mid-meeting

Convention: at most one `Race` with `state='NotStarted'` at a time (the pending race).

---

## Phases

### Phase 1 — Persist NextRace Lineup

**Goal:** Loading the NextRace page saves the lineup immediately. Refreshing recalls the same data — no recalculation.

**API changes:**

Replace `GET /drivers/nextrace/` with `GET /races/pending/`:
- Check DB for a `Race` with `state='NotStarted'`
- **If found:** load its `DriverRace` records, join driver names from `meeting_drivers`, return as `NextRaceSetup`
- **If not found:** calculate assignment (existing logic), then:
  1. Find the active meeting (most recent meeting with date <= today, or nearest upcoming)
  2. Find or create a `RaceSession` within that meeting
  3. Create `Race(state='NotStarted', session_id=<id>)` + one `DriverRace` per assigned driver, with `car_id` populated from `meeting_cars` where `meeting_id` and `lane` match
  4. Return as `NextRaceSetup`

This single endpoint is used by both the NextRace page loader and the LapCounter loader.

New endpoint `PUT /races/pending/lineup`:
- Accepts `[{driver_id, lane_number}, ...]`
- Updates the `DriverRace` records for the pending race
- Returns updated `NextRaceSetup`

---

### Phase 2 — NextRace UI Editing

**Goal:** Wire up the non-functional × and + buttons in NextRace.jsx.

**React changes (`NextRace.jsx`):**
- Add `useState` to hold mutable lineup (seeded from `useLoaderData()`)
- × button: remove driver from lane → call `PUT /races/pending/lineup` → update state
- + button: add driver from "Other Drivers" to an empty lane → call `PUT /races/pending/lineup` → update state

---

### Phase 3 — LapCounter Loads Pending Race

**Goal:** Driver names in LapCounter come from the pending race, not localStorage defaults.

**API changes:** None — `GET /races/pending/` already exists from Phase 1.

**React changes:**

`router.jsx` — add loader to `"/"` route:
```js
loader: async () => {
  const res = await fetch(`${import.meta.env.VITE_API_URL}/races/pending/`);
  if (!res.ok) return null;   // graceful fallback to localStorage defaults
  return res.json();
}
```

`LapCounter.jsx` — call `useLoaderData()`; if present, use `lane_assignments[i].driver_name` and `lane_assignments[i].id` to initialise driver state (overriding defaults). `carImgUrl` stays as localStorage / default for now.

Driver object mapping:
```
DriverWithLane.lane_number  →  driver.number   (1–6)
DriverWithLane.driver_name  →  driver.name
DriverWithLane.id           →  driver.driverId  (new field, needed for Phase 4)
```

---

### Phase 4 — Write Race Results Back

**Goal:** Lap events get written to the DB so the lane-assignment algorithm has real data.

**API changes:**
- `POST /races/{id}/start` — Race: NotStarted → Running
- `POST /races/{id}/laps` — record a `DriverLap`; body `{driver_id, lap_time}`; also updates `DriverRace.laps_completed`, `last_lap_time`, `fastest_lap_time`
- `POST /races/{id}/finish` — Race: Running → Finished; finalises `laps_completed` on each `DriverRace`

**React changes (`LapCounter.jsx`):**
- Store `raceId` in state (from Phase 3 loader)
- On race start: `POST /races/{raceId}/start`
- In `processLapMsg()` (MQTT callback): after updating local state, fire-and-forget `POST /races/{raceId}/laps`
- On race finish: `POST /races/{raceId}/finish`

All writes are fire-and-forget — errors are logged but never interrupt the UI.

---

### Phase 5 — After-Race Flow

**Goal:** After a race, a "Load Next Race" button resets LapCounter with the next lineup.

**UX:** Button visible in LapCounter only when `race.hasStarted && allDriversFinished`.

**On click:**
1. Fetch `GET /races/pending/` — finds no `NotStarted` race (old one is Finished), calculates and saves a fresh lineup
2. Reinitialise driver names from the new lineup
3. Reset race state

No new API endpoints needed.

---

## Critical Files

| File | Changes |
|------|---------|
| `api/app/main.py` | Replace `/drivers/nextrace/` with `/races/pending/`; add `/races/pending/lineup`, `/races/{id}/start`, `/races/{id}/laps`, `/races/{id}/finish` |
| `api/app/next_race.py` | Extract helpers: load pending race, save new pending race |
| `api/app/responsemodel.py` | Add `race_id` field to `NextRaceSetup` |
| `react/src/router.jsx` | Add loader to `"/"` route |
| `react/src/components/LapCounter/LapCounter.jsx` | Init from loader data; store `raceId`; POST on start/lap/finish; "Load Next Race" button |
| `react/src/components/NextRace/NextRace.jsx` | Wire edit buttons; call PUT endpoint |

---

## Recommended Build Order

1. **Phase 1** — persistence foundation (everything else depends on it)
2. **Phase 3** — loading into LapCounter (highest user-visible value)
3. **Phase 2** — editing in NextRace (quick wins, uses Phase 1 endpoint)
4. **Phase 4** — writing results (biggest change, enables algorithm to improve)
5. **Phase 5** — after-race flow (depends on Phase 4)

---

## Verification Checklist

- [ ] `/nextrace` loads → lineup shows → refresh → same lineup (no recalculation)
- [ ] Edit lineup (remove/add driver) → persists after refresh
- [ ] `/` loads → correct driver names in correct lanes
- [ ] Run a race → `driver_laps` table has records; `driver_races.laps_completed` updated
- [ ] After race, "Load Next Race" → LapCounter resets with new lineup
- [ ] `/nextrace` → shows fresh lineup for the following race
- [ ] `test_next_race.py` unit tests still pass after any `next_race.py` changes
