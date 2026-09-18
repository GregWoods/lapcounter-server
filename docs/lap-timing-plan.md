# Lap timing from Layer 1 counters: implementation plan

**Status:** planned on 2026-09-14, not started. `docs/lap-timing-clocks.md` explains *why*; this
file is *how*. The two hardware checks that decide lap 1's method, HW-11 and HW-12, exist in
`ble/hardware_check.py` but haven't been run. The plan works whichever way they come out: only
the choice of lap-1 method (plan A, B or C below) waits on them, and that is an environment
setting, not a code path.

## Decisions (Greg, 2026-09-14)

1. **Lap 1 is meaningful, even with jump starts allowed.**
2. **Start grid is a session setting.**
   - *In front of the finish line*: the first crossing completes lap 1, timed from lights-out.
   - *Behind the finish line*: the first crossing is discarded, and lap 1 is timed from it.

   This replaces the meeting-level `count_first_crossing` flag, which has the same meaning.
3. **Allow jump starts is a session setting**, since one meeting can use more than one track
   layout.
   - **A jump start is a sudden jump in throttle before lights-out, not a crossing.** There is
     one finish line, and it can sit well ahead of the back of a 2-lane, 6-car grid, or almost a
     full lap away. So a crossing can't measure a jump start, and only a Layer 1 that reports
     throttle can.
   - **How jump starts are detected and penalised is a later discussion**, outside this plan. See
     "Jump starts (later)". The setting itself is implemented now, in "Settings".
4. **The contract changes in one step.** No period of publishing old and new formats together.
5. **Lap-1 correlation, in order of preference:**
   - **Plan A.** `throttleTimestamp` as a clock heartbeat, if HW-12 finds it is a live reading
     of the Slot clock. It needs no power writes at all, so it works with jump starts allowed.
   - **Plan B** (Greg). Send commands 1 then 3 back-to-back **at arm**, while the cars are
     already still on the grid, so a moment at zero speed costs nothing. Lights-out is lapdata's
     own timer counting from arm, so go lands at a known point on the freshly reset clock. The
     error is the write latency, which HW-11 measures.
   - **Plan C.** Anchor on crossing stamps, as today. Last resort.
6. **Persisting provenance** (the raw counter on `driver_laps`) is not decided yet. See open
   question 1.

## What changed from the proposal

- **lapdata anchors to its own `time.monotonic()`, not the wall clock.** Setting the Pi's clock
  mid-meet then can't affect any lap, lap 1 included. Detecting a stepped clock is no longer
  needed for that. What remains of it is a guard against a Layer 1 that forgot to change epoch.
- **Correlation samples get their own topic, `layer1_clock`**, and every Layer 1 publishes them,
  GPIO included. lapdata never assumes that a Layer 1 shares its clock.
- **BLE starts a new clock when a halt begins, as well as when it ends.** Samples reported during
  a halt then can't corrupt the anchor for the clock that pre-halt laps were timed on.
- **uint32 wrap is Layer 1's job.** A wrap reads as the counter going backwards, which is a new
  clock, so lapdata never sees one.
- **Plan B at arm replaces option A at go** (commands 1 then 3 at lights-out). A reset at go made
  a creeping car stutter; a reset at arm doesn't.

## The contract

### `car_timestamp` (changed)

```json
{"car": 4, "lane": 1, "counter_ms": 897122, "clock": "ble:5f3a9c:7"}
```

`timestamp` is removed. `counter_ms` is an integer number of milliseconds, 0 or more. (The ARC
powerbase counts 10 ms ticks, not the ms its protocol doc claims, so `ble` multiplies by 10.
See `DEVICE_TICK_S`.) `clock` is
an opaque string, with these rules:

1. **Within one `clock`, `counter_ms` advances at real-time rate.**
2. **A Layer 1 starts a new `clock` whenever that stops being true, or might have.** That means
   when the counter stops (a halt), restarts, jumps backwards (a timer reset, a power cycle, a
   uint32 wrap), or might have done any of these unseen (a reconnect).
3. **A `clock` value is never reused**, including across container restarts, so it contains a
   random per-process part. Without that, a restarted `ble` would publish `ble:1` again, and
   lapdata would compare its counters with the old process's.
4. **lapdata only ever compares `clock` values for equality, and never parses them.** This is the
   same rule as for the `layer1` name in capability advertising.

⚠️ **Changing the clock is now the thing that can go wrong.** A Layer 1 that misses an event
reproduces the old post-halt bug. So every Layer 1 needs a test for every event that breaks its
counter.

### `layer1_clock` (new; internal to lapdata, like `car_timestamp`)

```json
{"clock": "ble:5f3a9c:7", "counter_ms": 897160}
```

This is a reading of the counter as Layer 1 sees it at that moment. lapdata pairs it with its
arrival time, and every `car_timestamp` doubles as one of these samples. **A sample must never be
early:** its `counter_ms` must not exceed the counter's true value at the moment it is published.
A sample that's late only overestimates the offset, and a running minimum ignores that, so late
samples are safe. This rule is also what lets plan B plug in without a special case, as the table
shows.

| Layer 1 | `counter_ms` | New `clock` when | `layer1_clock` samples |
|---|---|---|---|
| `ble`, `mocked-ble` | Slot StartFinish ms | connect; a backwards value; a write that halts or zeroes the clock (0, 1, 2, 4); the next write that restarts it (3) | Plan A: every Throttle notification, thinned to at most 10 a second by keeping the least-delayed one in each 100ms window. "Least-delayed" is judged on `ble`'s own monotonic clock, which is never published. Plan B: `counter_ms: 0` once the write that starts the clock from zero is acknowledged. HW-11's `clock` result says which write that is. Plan C: none. |
| `gpio` ×2, `mocked-gpio` | `CLOCK_MONOTONIC` in ms | never while the kernel is up: `gpio:<boot_id>`, which both lane containers share | once a second |

### `lap` and `driver_lap`

- **`lap`** keeps its shape. `lapTime` comes from counter differences, and `time` is a converted
  unix time. Nothing in `react/src` reads `lap` today.
- **`driver_lap`** gains `clock`, `counter_ms` and `timing`, where `timing` is `counter`,
  `anchored` or `from_go`. It's published either way. The DB writer ignores the new fields unless
  open question 1 says to persist them.

## lapdata

### New pure module: `lapdata/lap_clock.py`

```python
@dataclass(frozen=True)
class Crossing:
    clock: str
    counter_ms: int
    arrival: float          # lapdata's time.monotonic() when the message arrived

class ClockAnchors:         # thread-safe: timer threads read it too
    def observe(self, clock, counter_ms, arrival): ...   # running minimum per clock
    def to_local(self, clock, counter_ms) -> float | None
    def to_counter_ms(self, clock, local) -> float | None

def interval_s(a: Crossing, b: Crossing, anchors) -> tuple[float, str]:
    """Same clock: b.counter_ms - a.counter_ms, 'counter'. Different clocks: both ends
    converted through their anchors, 'anchored'. If an anchor has been evicted, fall back
    to arrival times."""

@dataclass
class RaceStart:
    local: float                        # lights-out, time.monotonic()
    counter_ms: dict[str, float]        # per clock, frozen the first time it is needed
```

- **The anchor** is a running minimum of `arrival - counter_ms / 1000`, kept separately for each
  clock. The last 8 clocks are retained, so a lap that spans a clock change can still convert its
  older end.
- **The divergence guard** is `ble`'s `CLOCK_STEP_THRESHOLD_S` / `CLOCK_STEP_CONFIRM_S` logic,
  moved here with its tests. It keeps the confirmation, so a delayed burst of samples can't
  trigger it. Since lapdata's own clock is monotonic, anything that trips it is a Layer 1 that
  forgot to change clock: re-anchor, and log at **ERROR** naming the clock.
- **Lap 1 from go:** `RaceStart.counter_ms[clock]` is computed from the anchor the first time any
  car's first crossing needs it, then frozen for the race. Every car on that clock therefore
  shares one correlation error: it can shift lap 1's absolute value, but it can't reorder lap 1
  times or positions.

### `race_manager.py`

- **Anchors are injected**, `RaceManager(anchors)`, so the module stays pure.
- **`start(go_local)`** records `RaceStart`. It also still sets `race_start_time = time.time()`,
  which is now for display and the `/races/{id}/start` POST only.
- **`on_lap(lane, crossing: Crossing)`:** lap 1 is `from_go` when `count_first_crossing`,
  otherwise `interval_s` from the discarded start crossing. Later laps use `interval_s` from the
  previous counted crossing.
- **`DriverState.last_crossing_time`** becomes `last_crossing: Crossing | None`, and `race_time()`
  becomes the interval from `RaceStart`. On one clock, that ranks cars by their counters exactly.
  ⚠️ Keep the regression that a discarded first crossing still sets `last_crossing`, or the
  initial positions fall back to lane order.
- **`lap_times`** entries carry `timing` and the crossing, for `driver_lap`.
- **`count_first_crossing`** keeps its name here and in `race_state`. It describes the behaviour;
  the start grid is the reason for it.

### `timestamps_to_lapdata.py`

- **Stamp `arrival = time.monotonic()` first thing in `on_message`**, before `_race_lock`. Time
  spent waiting for the lock would otherwise add to every sample's lateness.
- **Subscribe to `layer1_clock`** and feed `anchors.observe()`, without taking `_race_lock`.
- **`handle_car_timestamp` validates** that `counter_ms` is an int of 0 or more and `clock` is a
  non-empty string. Anything else, including the old `timestamp` format, is dropped and logged at
  ERROR: *"a Layer 1 image is older than lapdata"*. There's no fallback (decision 4). The deploy
  step makes sure there is no stale image to fall back from.
- **The phantom filter** keeps a `Crossing | None` per car and filters on `interval_s`. Lights-out
  resets it to `None`, instead of today's "now minus the minimum" trick.
- **`_lights_out`** takes `go = time.monotonic()` as its first line, before the lock, and passes
  it to `race.start(go)`. If the generation check then fails, the value is simply discarded.
- **Delete** `_crossing_ns`, `HW_TIMESTAMP_TOLERANCE_NS` and their tests.
- **Time expiry, `started_at` and logs** keep using the wall clock. They only need to be roughly
  right.

## Layer 1

### `ble/ble_to_timestamps.py`

- **Delete** `_device_to_wall()`, `_clock_offset`, `CLOCK_STEP_*`, `_step_run_*` and their tests.
  The guard moves to lapdata.
- **Add `_new_clock(reason)`**, which bumps a counter inside `f"ble:{secrets.token_hex(3)}:{n}"`
  and logs the reason. Every place that sets `_clock_offset = None` today calls it instead: on
  connect, on backwards values, and in `_note_command_applied()`. That last one now fires when a
  halting or zeroing write is applied (0, 1, 2, 4), as well as on the restarting one. If HW-11
  finds that command 1 zeroes the clock and then ticks, move 1 out of the halting set: it starts a
  new clock at the write, and command 3 is then not a restart.
- **One new clock per reset, not six.** Store the clock beside each car's `_last_start_finish`
  baseline, and only treat a value as *backwards* when that car's baseline is from the current
  clock. Otherwise every car's zeroed packet over the next rotation would start another clock.
  Crossing detection still compares against the baseline whatever clock it came from, because the
  powerbase's values run on continuously across a halt.
- **`publish_crossing()`** sends `counter_ms` as the raw `device_ms` value, plus `clock`.
- **Plan A:** `BLE_CLOCK_HEARTBEAT=throttle|none`, defaulting to `none`, and set to `throttle` on
  the Pi only once HW-12 passes. It subscribes to Throttle (`decode_throttle()` already exists)
  and publishes thinned `layer1_clock` samples. ⚠️ Keep the default off until then. A heartbeat
  from a *different* clock with a smaller offset would drag lapdata's anchor down, and a running
  minimum can't notice that. The same rule applies to the later throttle features (jump starts,
  fuel): if HW-12 finds a different clock, their throttle readings carry a clock id of their own,
  never the Slot clock's.
- **Plan B:** `BLE_RESET_AT_ARM=true`. On `race_control` `arm`, write 1 then 3, then publish the
  `counter_ms: 0` sample. Only turn it on if HW-12 fails and HW-11 isn't `not_reset`.
- **If HW-11 finds that re-sending 3 while racing resets the clock:** start a new clock on every
  such write, or stop re-sending it on `Running` and resume.

### `gpio/gpio_to_timestamps.py`, `gpio/mocked_timestamps.py`

These get minimal edits only, since the GPIO containers are due to be replaced rather than
refactored.

- **The counter is `time.monotonic_ns() // 1_000_000`**, taken in the interrupt callback. The
  clock is `gpio:` plus the first 8 characters of `/proc/sys/kernel/random/boot_id`, falling back
  to a random per-process id where there's no `/proc` (running `mocked_timestamps.py` natively on
  Windows).
- **A once-a-second `layer1_clock` heartbeat:** in `gpio_to_timestamps.py`'s `while True` loop,
  and as an extra task in `mocked_timestamps.py`.
- **No unit tests.** `gpio_to_timestamps.py` sets up GPIO pins at import. `mocked-gpio` is checked
  on the dev stack instead (see Verification).

### Mock powerbase

- **`SimulatedPowerbase.next_throttle_packet()`** fills `throttleTimestamp` from `device_ms`,
  tagged `# HW-12`. `mock_bleak` accepts a Throttle `start_notify` and pumps it every 50ms, also
  tagged `# HW-12`.
- **Command 1** is already modelled as zeroing and then ticking, tagged `# HW-09`. Retag it
  `# HW-11`.
- **After the hardware day,** correct both tags to match the report.

## Settings: start grid and jump starts

- **Migration `003-sessions-start-grid-jump-starts.sql`, re-runnable:**
  - Add `sessions.start_grid VARCHAR(20) NOT NULL DEFAULT 'BehindLine'`, with a CHECK that it is
    `'InFrontOfLine'` or `'BehindLine'`. The default matches today's
    `count_first_crossing = false`.
  - Add `sessions.allow_jump_starts BOOLEAN NOT NULL DEFAULT true`, which is today's behaviour:
    nothing prevents or flags a jump start.
  - In a `DO` block guarded on the column still existing: copy `meetings.count_first_crossing` into
    each session's `start_grid`, then drop the meetings column.
  - ⚠️ The old API image selects that column, so it breaks the moment the migration runs. Apply
    the migration and deploy the new API together.
- **API:** `RaceSession.start_grid` and `allow_jump_starts`, plus the Create/Update models. Remove
  the flag from `Meeting`, `MeetingCreate` and `MeetingUpdate`, and from `schema.sql`,
  `sampledata.sql` and `sampledata.py`. In `next_race.py`, set
  `count_first_crossing = race_session.start_grid == 'InFrontOfLine'`, and add
  `allow_jump_starts` to `NextRaceSetup`.
- **lapdata:** `_load_pending` passes `allow_jump_starts` through into `race_state`, so whatever
  later enforces it (lapdata's detection, or `ble` if power is held) already has it.
- **Admin:**
  - Remove the meeting checkbox and its "· Count first crossing" badge.
  - Add a session **Start grid** select: *Behind the finish line (the first crossing starts
    lap 1)* / *In front of the finish line (the first crossing is lap 1)*.
  - Add an **Allow jump starts** checkbox, ticked by default, with a hint saying truthfully that
    it isn't enforced yet. Once capability advertising exists, grey it out unless `throttle` is
    advertised.

## Jump starts (later)

Deliberately out of this plan: how a jump start is detected (thresholds, what counts as
"sudden"), what it costs the driver, and whether power is also held until lights-out. Those are
for a later discussion. What this plan fixes in place for that work:

- **It's measured from throttle, not crossings** (decision 3), so it needs the `throttle`
  capability, and GPIO can never offer it. The `allow_jump_starts` setting already exists by then
  (migration 003) and reaches `race_state`; this work only has to act on it.
- **Placing a throttle jump before or after lights-out is a clock question**, answered the same
  way as lap 1: convert go onto the throttle's clock once per race (`RaceStart`), and compare the
  throttle's own timestamp rather than its arrival. A squeeze tens of milliseconds before go can
  arrive after it.
- **HW-12 records each controller's highest throttle reading at rest** (`throttle_at_rest_max`),
  the noise floor any threshold will have to sit above.

## Order of work

1. **Settings.** Migration 003, API, lapdata passthrough, and the Admin start grid and jump-start
   settings. These are independent and can ship alone.
2. **lapdata's pure core.** `lap_clock.py`, `race_manager` on `Crossing`s, and tests. Behaviour
   doesn't change until step 3 wires it in.
3. **The switch, as one commit.** lapdata wiring, `ble`, `gpio`, `mocked-gpio`, the mock's
   Throttle, test updates and the CLAUDE.md contract. Plan C is the default, which already gives
   lap 2 onwards exact counter differences.
4. **Hardware day.** HW-01 to HW-12 plus the E checks. Choose plan A, B or C, set the env var, and
   correct the mock's tags.
5. **Provenance persistence**, if open question 1 says yes. Migration 004 and dbwriter.
6. **Jump starts:** a separate design discussion, after capability advertising.

Aim to finish steps 1–3 before the hardware day, so that day validates the final code.

## Tests

**`lapdata/test_lap_clock.py`**
- The anchor is a running minimum per clock. Clocks are independent, and old clocks are retained
  up to the limit.
- The divergence guard re-anchors after its confirmation period and logs an error; a delayed burst
  doesn't trigger it.
- Same-clock intervals are exact however jittery the arrivals are. A cross-clock interval uses the
  anchors.
- A `counter_ms: 0` sample published after a reset anchors to within its lateness.

**`lapdata/test_race_manager.py`** (adapted)
- Lap 1 from go uses the frozen per-clock start. Two cars' lap-1 errors are identical even when
  the anchor improves between their crossings.
- `count_first_crossing = false`: lap 1 is exact even with a deliberately wrong anchor.
- The discarded first crossing still sets `last_crossing` (existing regression).
- On one clock, positions follow the counters even when arrivals are out of order.
- A lap spanning a halt's clock change is `anchored` and includes the halt.

**`lapdata/test_timestamps.py`** (rewritten)
- An old-format `car_timestamp` is dropped with an error.
- The phantom filter works on counters.
- Arrival time is stamped before the race lock; lights-out's local time is taken before the lock.

**`ble/test_ble_to_timestamps.py`**
- The crossing payload carries the raw counter and the clock.
- A new clock starts on: connect, a halting write, a restarting write, backwards values (exactly
  once across the six cars' zeroed packets), and a wrap. Repeated `POWER_ON_RACING` writes don't
  start one.
- Clock ids differ between processes.
- Heartbeat thinning keeps the least-delayed sample in each window, and nothing is published when
  the heartbeat is disabled.
- Plan B's zero sample comes after the acknowledgement, on the new clock.

**`ble/test_mock_scenarios.py`**
- Through the real `run()`, feed `lap_clock` from the published messages and compare lap 2 onwards
  with the simulator's ground-truth crossings, to 1ms, across a halt, a reconnect and a power
  cycle.

## Verification on the dev stack

Restart `lapdata` and `mocked-ble`, then run a race through `race_control`:
- Laps count, and lap 1 is plausible for both start grid settings.
- A yellow flag and resume log a new clock at the halt and again at the resume, and later laps
  are sane.
- `docker restart mocked-ble` mid-race causes no phantom laps and the laps continue.

Then stop `mocked-ble`, bring up `--profile mocked-gpio`, and repeat the laps check.

## Deploy

- **Build and push every image:** `ble`, `gpio`, `lapdata`, `api` and `react`, plus `dbwriter` if
  step 5 has happened. ⚠️ The `gpio` image matters even though `ble` is the default. `-Layer1 gpio`
  is the race-day fallback, used offline where nothing can be rebuilt, and an old image would
  count no laps at all.
- **Apply migration 003 immediately before `deploy.ps1`,** which runs no migrations.
- **On the Pi, prove both Layer 1s:** E1 on `-Layer1 ble`, then a few laps on `-Layer1 gpio`.
- **New checks in `ble/HARDWARE_VALIDATION.md`:**
  - **E9 lap 1:** with the grid in front of the line, stopwatch lights-out to the first crossing.
  - **E10 yellow and resume:** `ble` logs a new clock at the halt and at the resume.
  - **E11 GPIO fallback:** laps count.

  E3's expected log line changes from "re-anchoring the clock offset" to a new clock.

**Docs to update in the switch:**
- **CLAUDE.md:** the `car_timestamp` contract, a `layer1_clock` topic row, the "BLE anchors the
  powerbase's clock" paragraph (it becomes the clock rules above), the `HW_TIMESTAMP_TOLERANCE_NS`
  paragraph, and "Discarded first crossing" (now the session start grid).
- **`ble/HARDWARE_VALIDATION.md`:** HW-02, HW-06 and HW-10's "code that assumes it" columns.
- **`docs/mocked-ble-plan.md`:** the Throttle simulation.
- **`docs/lap-timing-clocks.md`:** status.

## Open questions for Greg

1. **Persist provenance** (`clock`, `counter_ms`, `timing`) on `driver_laps`? Recommended: yes.
   It's one migration adding nullable columns, and it is the only way to re-check a disputed lap
   after the meet. Cheap now; impossible for laps already raced.
2. **With the grid just behind the line, a car that creeps across it before lights-out.** This
   is lap bookkeeping, not jump-start detection (see decision 3). That crossing is ignored today,
   since the race isn't `Running`. The car's first crossing after go is then discarded as its
   start crossing, so **it loses a whole lap.** Recommended: a crossing during `ArmedForStart`
   becomes that car's start crossing, so its lap count stays right. Any penalty belongs to the
   later jump-start discussion.
3. **A lap that spans a yellow-flag halt.** Keep including the halt's duration? That's today's
   behaviour and matches a stopwatch. Recommended: keep it. The lap is slow, so it can never be a
   fastest lap, and excluding the halt would need the halt to be timed exactly, which is precisely
   the error-prone part.
