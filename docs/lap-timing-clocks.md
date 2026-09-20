# Lap timing: Layer 1 counters instead of wall-clock timestamps

**Status:** design rationale, kept for the *why*. **The contract change described here was
implemented on 2026-09-20** (plan steps 2 and 3) — this document now describes the problem
it solved, not pending work. Greg's decisions and the implementation plan are in
**`docs/lap-timing-plan.md`**, which also records where the implementation deviates from it;
where the two differ, the plan wins. HW-12 was run and passed on 2026-09-20, so option B
below (the plan's plan A, the Throttle heartbeat) is what shipped.

⚠️ **The plan renames the lap-1 options.** Its *plan A* is option B below (the Throttle
heartbeat). Its *plan B* is Greg's reset with commands 1 then 3 **at arm**, which replaces
option A (the same reset at go). Its *plan C* is option C.

## The principle (Greg)

Lap times need to be accurate. Everything else only needs to be roughly right. So **lap
times should come only from differences between Layer 1's own timestamps**, and never
from a conversion to the Pi's clock where that can be avoided.

## How it works today

- **BLE Layer 1** (`ble/ble_to_timestamps.py`): the powerbase stamps each crossing in
  device 10 ms ticks (the protocol doc says ms; the hardware disagrees) (uint32, counting from its last timer reset). `_device_to_wall()`
  converts that to unix time as `device_ms/1000 + _clock_offset`, and only the result is
  published in `car_timestamp.timestamp` (ns). `_clock_offset` is a running **minimum**
  of `arrival - device_ms/1000`, where `arrival` is `time.time()` in the Slot callback.
  It is reset on connect, when the device clock jumps backwards, and when a write
  restarts a halted clock. A separate check re-anchors after a forward step in the Pi's
  clock (`CLOCK_STEP_THRESHOLD_S`/`CLOCK_STEP_CONFIRM_S`).
- **GPIO Layer 1** (`gpio/gpio_to_timestamps.py:70`) and `mocked_timestamps.py`: stamp
  `time.time_ns()` in the callback.
- **lapdata** (`lapdata/timestamps_to_lapdata.py:_crossing_ns`) trusts `timestamp` if
  it is within 30s of its own clock (`HW_TIMESTAMP_TOLERANCE_NS`), and otherwise uses
  arrival time. `race_manager.on_lap` times lap 1 as `crossing - race_start_time`
  (`race_start_time = time.time()` at lights-out) and later laps as the difference from
  the previous crossing. `MINIMUM_LAP_TIME` filters on the same values.

## What's wrong with it

1. **Layer 1 quietly depends on a clock it doesn't own.** BLE is never told about
   lapdata's clock. It just calls `time.time()`, which only matches because both
   containers share the Pi's kernel. That assumption isn't written down anywhere, and a
   Layer 1 on another machine would convert to the wrong clock. The 30s tolerance in
   lapdata exists precisely because Layer 1's clock isn't trusted.
2. **The raw value is thrown away at the bottom of the stack.** `device_ms`, the arrival
   time, the offset in use and the anchor epoch are all lost. A disputed lap can't be
   checked or recomputed afterwards.
3. **The anchor adds error to lap times.** *(Follows from the design, not measured.)*
   The running minimum only ever moves down. Each time it drops by δ, every later
   crossing is stamped δ earlier, so **the lap spanning that drop reads δ short**. Just
   after an anchor starts, δ can be as big as one Slot round-robin rotation (~300ms in
   the mock, real value is HW-02). Anchors restart on reconnect and after every
   yellow-flag halt, which puts the worst of this mid-race.
4. **GPIO lap times follow the wall clock.** A lap during which the Pi's clock is set,
   whether by hand from the laptop Home page or by NTP, is wrong by the size of the step.

## Proposal: Layer 1 publishes a counter plus an epoch

```json
{"car": 4, "lane": 1, "counter_ms": 897122, "clock": "ble:7"}
```

**Contract rule (hardware-neutral):** within one `clock` value, `counter_ms` is a
monotonic millisecond counter running at real-time rate. When `clock` changes, values
from before and after can't be compared. lapdata never learns *why* it changed.

| Layer 1 | `counter_ms` | `clock` changes when |
|---|---|---|
| `ble`, `mocked-ble` | Slot StartFinish device ticks (10 ms) | reconnect; device ticks jump backwards (commands 0/1, power cycle); a write restarts a halted clock (commands 2/4 → 3) |
| `gpio` (×2 containers), `mocked-gpio` | `CLOCK_MONOTONIC` in ms, which all containers on one kernel share | boot only (e.g. an id taken from `/proc/sys/kernel/random/boot_id`) |

⚠️ **The epoch is now the thing that can go wrong.** A Layer 1 that forgets to change it
after a halt reproduces today's post-halt bug. Each Layer 1 needs a test that shows the
epoch changes on every event that breaks the counter.

### What lapdata then does

| Calculation | How | Needs the Pi clock? |
|---|---|---|
| Lap 2 onwards | `counter` difference, same epoch | **no** |
| `MINIMUM_LAP_TIME` filter | `counter` difference | no |
| Crossing order (positions) | compare counters, same epoch | no |
| Lap 1 | `crossing_counter - start_counter_ms` (see below) | yes, once per race |
| A lap spanning an epoch change | convert both ends to Pi time | yes, least accurate |
| Time-expiry, DB times, logs | convert to Pi time | yes, rough is fine |

- **uint32 wrap:** the counter wraps after 49.7 days. That's unlikely during a meet, but
  handle it rather than leave a latent bug.
- **Powerbase clock drift** (HW-10) affects lap differences by ppm. At 100ppm on a 5s
  lap that's 0.5ms, which can be ignored.
- **The anchor logic moves from `ble/` to lapdata:** the running minimum, clock-step
  detection and their tests. Step detection belongs with the clock that steps.
  Backwards detection becomes Layer 1's job, expressed as an epoch change.
- **The raw provenance question goes away**, because the raw value *is* the contract.
  It could optionally be carried through `driver_lap` into a `driver_laps` column.

## Where arrival time still matters

Arrival is the only point where a Layer 1 counter and the Pi's clock are seen together.
Each arrival gives one slightly late `(counter, pi_time)` pair, which is why the anchor
keeps the minimum. Under this proposal it is only needed for the "yes" rows above,
chiefly lap 1. Nothing else needs the anchor to be accurate.

## The lap 1 problem

Lights-out is lapdata's own timer on the Pi, so lap 1 is the one lap timing that must
connect Layer 1's clock to the Pi's clock.

### The powerbase's intended lifecycle

From the command table in `ble/reference/Scalextric_ARC_BLE_Protocol.md`:

| Cmd | Power | Cars move? | Timestamps | Doc's "usually used as" |
|---|---|---|---|---|
| 0 `NO_POWER_TIMER_STOPPED` | off | no | reset to 0 | save mode |
| 1 `NO_POWER_TIMER_TICKING` | on | no (all speeds 0) | zeroed | ready mode |
| 2 `POWER_ON_RACE_TRIGGER` | on | not stated | halt | yellow flag |
| 3 `POWER_ON_RACING` | on | yes | ticking | normal game mode |
| 4 `POWER_ON_TIMER_HALT` | off | no | halt | game halt |

So the design Scalextric intended is **command 1 on the grid, command 3 at go**: the
timers start at the start, and lap 1 is on the powerbase's own clock.

**No documented command resets the clock while cars can move.** Only 0 and 1 reset it,
and both stop the cars. With an "allow jump starts" option, power stays on
throughout, so the powerbase can't know when go is and **some correlation is
unavoidable**.

### Options

**A. Reset at go: write 1 then 3 back-to-back at lights-out.**
- Error: BLE write latency. A write-with-response brackets it, since the reset happened
  between sending the write and receiving the acknowledgement.
- Cost: cars get zero speed for as long as two writes take. That's harmless on a
  stationary grid (no jump starts). With jump starts allowed, a creeping car would
  stutter, and only a real track can show whether that's noticeable.
- Unknown: does command 1 zero the clock once and then tick, as its name says, or hold
  it at zero until command 3? If it ticks, the gap between the two writes ends up in
  lap 1.
- The reset shows up as the clock jumping backwards, which is an epoch change, so the
  contract handles it with no special case.

**B. Correlate using the Throttle characteristic's timestamp.**
- `0x3B09` notifies several times a second, and bytes 7–10 are `throttleTimestamp`:
  "when the throttle packet was last updated, in milliseconds". That is close to a live
  reading of the device clock. A crossing stamp can be up to a whole rotation old.
- Error: about one notification delay rather than one Slot rotation, and samples arrive
  continuously, even when no cars are moving, so the anchor has settled before
  lights-out.
- Never touches power, so it works with jump starts allowed.
- Unknown: is it the **same timer** as the Slot stamps, and does it halt and zero with
  the same commands?
- Would need Layer 1 to publish correlation samples, e.g. a
  `{"clock": "ble:7", "counter_ms": ...}` heartbeat that lapdata pairs with arrival
  time. The design isn't finished.

**C. Correlate using crossing stamps (today's method).** The fallback if neither A nor B
holds up on hardware.

A and B are both probably tens of milliseconds. The hardware checks should decide
between them.

### Make the correlation error the same for every car

- **Convert lights-out to counter time once per race** (`start_counter_ms`), then time
  every car's lap 1 as `crossing_counter - start_counter_ms`. Any correlation error is
  then **identical for every car**. It can't change lap-1 order or finishing positions,
  only the absolute lap-1 value. Today each car's lap 1 uses whatever anchor held when
  *that car* crossed, and the anchor can improve between cars.
- ~~**`count_first_crossing = false` removes the problem entirely.** The first counted lap
  is then already a crossing-to-crossing difference, with no correlation involved.~~
  ⚠️ **Wrong — corrected by Greg on 2026-09-20** (see `docs/lap-timing-plan.md` decision 2).
  Lap 1 is timed from **lights-out in every race**, whatever the start grid; the grid only
  decides which crossing *ends* it. So there is no escape hatch: **every** race's lap 1 goes
  through the correlation, which makes the heartbeat (option B below, the plan's plan A)
  matter always rather than sometimes.
- An absolute lap-1 error still matters in one case: lap 1 counts, it is eligible for
  fastest lap, and the error shortens it.

## Hardware checks to add (`ble/hardware_check.py`, `HARDWARE_VALIDATION.md`)

Suggested numbering continues from HW-10.

- **HW-11: command 1 → 3 at go.**
  - Does the clock start from 0 at command 3, or tick from command 1?
  - What is the write latency (time from send to acknowledgement) for each write?
  - Does a moving car visibly stutter during 1 → 3?
  - Does re-sending 3 while already racing reset anything? (probably not; cheap to check)
- **HW-12: `throttleTimestamp`.**
  - Does it share the Slot timer: same value range, and does it zero on 0/1 and halt on 2/4?
  - How current is it: its value compared with arrival time, as a spread over many
    notifications?
  - What is the notification rate?

Both run on the hardware day, together with HW-06/07. The mock (`ble/mock_powerbase.py`)
should then be corrected to match, tagged the same way as the existing HW-xx assumptions.

## Is this Scalextric-only?

Concern raised by Greg: this could become a design for Scalextric alone, when Layer 1
might one day come from systems outside our control, such as Carrera. That's unlikely
for now, but worth keeping cheap.

**The contract and lapdata are no less neutral than today, and probably more.**
- Lap-counting hardware commonly stamps crossings on its own internal clock. As I
  remember it, *not verified here*, Carrera's Control Unit reports a millisecond timer
  value per crossing, and the community `carreralib` models it that way. A hardware
  counter plus an epoch is the natural thing for such a device to publish.
- Hardware with no clock of its own (GPIO, a bare sensor) uses a monotonic clock, as
  shown above.
- Today's contract is the one with the hidden assumption: that Layer 1 reads the same
  wall clock as lapdata.

**The Scalextric-specific parts must stay inside the BLE Layer 1:** command 1 → 3,
`throttleTimestamp`, HW-11/12. The guardrail:

> lapdata's algorithm is identical for every Layer 1. It always derives
> `start_counter_ms` from correlation samples, and never assumes the counter was reset
> at go. A Layer 1 may *improve* the correlation (reset at go, a Throttle-based heartbeat),
> but only through the generic contract: an epoch change, or better `(clock, counter)`
> samples.

So option A is a way for BLE to give lapdata better data, not something lapdata relies
on. Other hardware without it just gets a less accurate lap 1, not a different code path.
Keeping this rule is what stops the design becoming Scalextric-only. It is the same rule
as capability advertising: branch on what the data says, never on which hardware sent it.

## Answered (Greg, 2026-09-14)

1. **Lap 1 is meaningful, even with jump starts allowed.** A session-level start grid
   setting decides whether the first crossing counts: *in front of the finish line* counts
   it as lap 1, *behind* discards it. This replaces the meeting-level `count_first_crossing`.
2. **"Allow jump starts" is a session setting**, because one meeting can use more than one
   track layout. A jump start is a sudden jump in **throttle** before lights-out, never a
   crossing: the finish line can be almost a lap from the back of the grid. How jump starts
   are detected and penalised is a later discussion.
3. **Switch the contract in one step.**
4. **Persisting provenance:** still open. See the plan's open questions.

Greg also proposed plan B: if `throttleTimestamp` turns out to be a different clock, send
commands 1 then 3 at **arm**, when the cars are already still, rather than at go.

## Scope when it's implemented

- **Contract:** `car_timestamp` section of CLAUDE.md, and any other docs that describe it.
- **Layer 1:**
  - `ble/ble_to_timestamps.py`: stop converting, add the epoch.
  - `gpio/gpio_to_timestamps.py`, `gpio/mocked_timestamps.py`: monotonic counter plus
    boot epoch.
  - `mocked-ble` needs nothing beyond the real code, but `mock_powerbase.py` gets the
    HW-11/12 behaviours.
- **lapdata:** `_crossing_ns` becomes counter/epoch handling. It gains the anchor (moved
  from `ble/`, with its tests), `start_counter_ms`, uint32 wrap handling, and a
  `race_manager` that computes laps from counter differences.
- **Tests:** every Layer 1 changes epoch on every event that breaks the counter.
  lapdata tests: the anchor, lap 1 error being the same for every car, laps spanning an
  epoch change, wrap.
- **Optional:** carry provenance through `driver_lap` and dbwriter, which needs a
  migration.
