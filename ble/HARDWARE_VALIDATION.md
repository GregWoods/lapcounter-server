# BLE Layer 1: hardware validation

`ble` is the live Layer 1 but has never run against a real Scalextric ARC Pro powerbase.
The unit tests prove the code does what it *intends*; they can't prove the powerbase
behaves the way the code *assumes*. This file lists exactly those assumptions, and
`hardware_check.py` tests each one against the hardware.

**Do this before the first meet on BLE.** HW-06 and HW-07 matter most: they decide
whether yellow-flag power cuts keep lap times right and whether they're safe. HW-11 and
HW-12 decide how lap 1 is timed in the lap-timing redesign (`docs/lap-timing-plan.md`).

## 1. Run the scripted checks

Takes about 30 minutes. You need one car per controller, and ideally a stopwatch. Never
run it during a race: it cuts track power, and HW-09, HW-11 and HW-12 zero the lap timers.
Run HW-12 in the same run as HW-06 and HW-11 (a full run does), because it compares
against their results.

**On the Pi.** The script ships in the ble image once `ble/build-and-push-ble.ps1` has
been run after this change.

```bash
docker stop ble                     # the powerbase accepts one BLE connection at a time
docker run --rm -it -v /var/run/dbus:/var/run/dbus --cap-add NET_ADMIN -v "$PWD:/out" \
    -e BLE_ADDRESS=AA:BB:CC:DD:EE:FF \
    gregkwoods/lapcounter-server-ble:latest python hardware_check.py --report /out/hw-report.json
docker start ble
```

**On the laptop,** if it has Bluetooth. This is quicker to iterate on.

```powershell
pip install bleak paho-mqtt
python ble/hardware_check.py --report hw-report.json
```

To re-run a subset, add `--only HW-06,HW-07`. `--drift-minutes 10` lengthens HW-10.

**HW-03 takes no keyboard input at all**, so it can be started and then left alone while both
hands are on a controller: `--only HW-03`, hold one trigger fully down, and the sweep begins
as soon as the script sees it and steps the power every 2s. Watch the car, and report what it
did at each step afterwards. ⚠️ Be ready for the failure case physically — if a zero
multiplier does not stop the car, it keeps going at full throttle.
The report is rewritten after every check, so an aborted run keeps its results. Each
check ends with a verdict:
- `pass`: the hardware matches the code.
- `fail`: it doesn't.
- `review`: the answer changes code or race-day procedure; see `code_impact` in the report.
- `info`: a measurement, not a yes/no.

## HW-03, 2026-09-20: the power multiplier works, and does not touch the counter

Run on the `lapcounter-ble` box against the real ARC Pro, car 5, trigger held flat:

| step | byte | trigger read | counter rate | car |
|---|---|---|---|---|
| 100% | `0x3f` | 63 | 1.0 | full speed |
| 75% | `0x2f` | 63 | 1.0 | distinctly slower |
| 50% | `0x20` | 63 | 1.043 | slower again |
| 0% | `0x00` | 63 | 1.0 | **stopped** |

**Verdict: `CARS_STOPPED` is correct.** A zero multiplier under `POWER_ON_RACING` stops a
car whose trigger is held flat, and the counter runs at real-time rate straight through the
stop — so the lap spanning a yellow flag stays an exact counter subtraction with the
stopped time in it, and no clock change is needed. Command writes were accepted at 58-133ms.

Three things this run taught, all of which cost an hour:

1. ⚠️ **`docker stop ble` does not free the powerbase.** BlueZ keeps the ACL connection
   open on the host, so the base stays `Connected`, never advertises, and nothing else can
   reach it — a scan finds nothing and a direct connect fails with
   `BleakDeviceNotFoundError`. `bluetoothctl disconnect EF:2A:C2:EF:D8:AA` is required too.
2. **The production container never scans** (`BLE_ADDRESS` is set), so `hardware_check.py`
   now falls back to connecting by address when a scan doesn't see the device.
3. ⚠️ **The operator cannot see this script's output while it runs** — it is driven over
   ssh and the stream only arrives at the end. An instruction printed here reaches them too
   late to act on, which silently produced eight seconds of released-trigger data that read
   exactly like "the powerbase reports no throttle at all". Hence the self-synchronising
   protocol: the sweep starts on the first packet showing the trigger down and retries until
   it gets one with the trigger held throughout. It took 5 attempts here.

⚠️ **Controller calibration is an untested assumption** (Greg, 2026-09-20): a released
trigger may report a small non-zero value and a fully-pulled one somewhat under 63. Car 5's
controller read a clean 0 and 63, so `TRIGGER_HELD_THRESHOLD = 0x30` was comfortable — but a
controller reading, say, 40 at full travel would never be detected as held, and the sweep
would wait forever. `throttle_max_seen` in the report is there to diagnose that.

## First run: 2026-09-18 (Pi Zero 2 W, one car, ID 5)

The protocol doc is wrong about units: **Slot and throttle timestamps count 10 ms ticks,
not ms** (`DEVICE_TICK_S`). Read as ms, every lap came out ~10x short and fell under
`MINIMUM_LAP_TIME`, so BLE would have counted nothing at a meet. That run's HW-06, HW-11,
HW-12 verdicts and HW-10's lateness/drift were computed in the wrong unit. Re-read in ticks:

- HW-01, HW-05, HW-09 pass. HW-06: power cut and restore pass, and the clock **pauses**
  through a halt, as `_note_command_applied()` assumes.
- HW-11: command 1 zeroes the Slot timers and holds them at 0 until command 3, but does
  **not** hold the cars still.
- HW-12's `different_clock` came from the unit error: throttleTimestamp also runs at the
  0.1x rate, froze through the halt and zeroed with the Slot timers. Re-run it.
- HW-02: **no Slot packets at all until the first Command write** (after HW-08's power
  cycle too). Slot packets came every ~300 ms, so a **~1.8 s rotation** over 6 car IDs:
  the worst-case delay before a crossing reaches the leaderboard. Throttle notifications
  also came every 300 ms, much slower than the doc's 20–40 ms connection interval
  suggests. Unexplained so far: it may be the Pi Zero's link, not the powerbase.
- HW-07 needs re-running. The racing case's "timestamps not retained" was probably the car
  being driven while disconnected.

Re-run with one car, no drift test: `--only HW-02,HW-06,HW-07,HW-11,HW-12,HW-13`.

## Second run: 2026-09-18, after the tick fix

- **HW-06 pass**: power cut/restore work, and the clock pauses through a halt.
- **HW-07 pass**: disconnected while halted, the track **stays unpowered**, even after reconnecting
  before any write (the safety case). Disconnected while racing, power stays on. Timestamps are
  kept across a reconnect.
- **HW-11**: command 1 zeroes the timers and holds them at 0 until command 3 (`started_at_go`), so
  plan B's zero is the command-3 write. Command 1 does **not** hold the cars. Re-sending command 3
  mid-race leaves the clock alone.
- **HW-12**: throttleTimestamp runs at 1.0x in ticks, **advances at rest**, halts and zeroes with
  the Slot clock. The offset comparison wasn't gathered (no crossings in the driving window), but
  everything else says same clock, so plan A is back in play. Re-run HW-12 to settle it.
  *(Settled in the third run below: pass.)*
- **HW-02**: Slot packets are **20 bytes**, not 18. They also arrived before any Command write
  this time, but the base had been left in `POWER_ON_RACING`. The cadence is confirmed: one packet
  every 300 ms, all 6 IDs whether or not a car is present, so **1.8 s per car**. `btmon` shows
  a 37.5 ms connection interval (inside the doc's 20–40 ms), Slot and Throttle notifying in
  lockstep, and asking BlueZ for 20 ms changed nothing. The pace is the powerbase's, not the link's.
- **HW-13**: the base buttons have no documented field. The only change while pressing was
  Throttle byte 18 (car 5's `ctrlVersion`) reading 0xFF, and the button LEDs flashed
  inconsistently even on single clicks. It looks like a side effect of pairing mode, not a
  button report, so it is not usable as a race-control input.

## Third run: 2026-09-20 — HW-12 settled, plan A confirmed

**HW-12 pass**: `conclusion: same_clock`, `live_at_rest: true`, `offsets_agree: true`, over 10
crossings. **`throttleTimestamp` is a live reading of the Slot clock, so plan A is on**: `ble` can
publish it as a `layer1_clock` heartbeat and lap 1 needs no power writes at arm or go
(`docs/lap-timing-plan.md` decision 5).

| | at rest | driving |
|---|---|---|
| notifications | 34 in 10s | 225 in 67s |
| median gap | 300 ms | 300 ms |
| advancing fraction | 1.000 | 1.000 |
| device:wall rate | 0.9962 | 0.9989 |
| lateness median / p95 / max | **1 / 39 / 39 ms** | 38 / 38 / 76 ms |

- **Throttle notifications are 3.3/s (one per 300 ms), not the "several times a second" the
  protocol doc implies** — the same cadence as Slot packets, consistent with the 37.5 ms
  connection interval measured in the second run. Still ~15x more often than crossings at
  ~5 s laps, which is the whole point.
- **Lateness at rest is a median of 1 ms**, so on a stationary grid the anchor converges to a
  few ms almost immediately. The arm countdown is ~7.2 s ≈ 24 throttle packets, so lap 1
  starts with an essentially exact anchor. Contrast the race measured the same day, where the
  *crossing* anchor started 1.56 s high and took 3 crossings to converge, making lap 1 read
  long and laps 1–2 read short (see "the anchor converges" in CLAUDE.md).
- **The two anchors agree to 148 ms** (`slot_minus_throttle_ms: 148`, tolerance 500 ms). The
  sign matters: `slot_offset` is the *higher* of the two, so even after 10 crossings the
  crossing-based anchor was still 148 ms less converged than the throttle one. That 148 ms is
  what plan A removes from lap 1.
- **`throttle_at_rest_max: [0,0,0,0,0,0]`** — every controller reads a clean zero at rest, so a
  future jump-start threshold has no noise floor to clear.

⚠️ **The corroboration is cross-run, not simultaneous.** `evidence` shows `halt_matches_slot:
null` and `zeroing_matches_slot: null` because HW-06 and HW-11 weren't in this run, so
`conclude_same_clock()` reached `same_clock` on the offsets alone. The throttle clock's own
measurements were checked by hand against the second run instead: it went `halted` through the
power cut (`device_s 0.0` across `wall_s 9.037`, vs Slot "pauses", HW-06), and `zeroed: true`
held at `0` for 4.2 s until command 3 (vs Slot "zeroes and holds until command 3", HW-11). Both
match, and two free-running timers would have to start within 148 ms of each other *and* both
freeze on command 4 *and* both zero on command 1. Good enough to build on; run HW-06, HW-11 and
HW-12 together on the next full run to close it properly.

**Running HW-12 unattended.** The prompts were gated on marker files rather than Enter, so the
windows could be opened and closed remotely one step at a time (the driving prompt's *duration*
is the measurement window — `check_throttle_clock()` stamps `driving_from` before the prompt).
The `ask_yes_no` stand-in returned `None` rather than inventing an observation.

⚠️ **`docker stop ble` leaves BlueZ holding the link.** It SIGKILLs (exit 137) with no clean BLE
disconnect, so `bluetoothctl info <mac>` still says `Connected: yes`, the powerbase stops
advertising, and `find_device_by_address` fails with the misleading *"No powerbase found. Is it
on, in range, and is the ble container stopped?"* — with the container demonstrably stopped.
Before any hardware run:

```
docker stop ble && bluetoothctl disconnect EF:2A:C2:EF:D8:AA
```

## Throttle cadence and fuel integration (2026-09-20)

190 Throttle notifications over 56.7 s of real driving, captured raw to settle two questions.

**1. The 300 ms cadence is the powerbase's, not the Pi's BLE stack.** Two independent proofs:

- **`packetSequence` (byte 0) is counted at the source** — it increments once per notification the
  base *sends*, so coalescing in BlueZ would show as deltas > 1. Observed: **delta 1 on 188 of 189
  transitions (99.5%)**, with a single delta of 2. One dropped packet in 190; everything else the
  base sent, we got.
- **The base's own clock declares the rate**: `throttleTimestamp` advanced by **median 300 ms, min
  300, max 300** — zero variance. The powerbase stamps each packet exactly 300 ms after the last.

With the second run's `btmon` evidence (a 37.5 ms connection interval, so the link could carry ~8x
this), that closes it. The host *does* add jitter but not rate limiting: inter-arrival gaps were
min 33 ms / median 300 / max 567 ms (the 33 ms a pair delivered back-to-back after a scheduling
stall, the 567 ms the lost packet). That jitter is exactly what the clock anchoring keeps out of
lap times.

**2. 3.3 Hz undersamples the signal, but the integral still converges.**

- Median change between consecutive samples: **20** of a 0–63 scale (p95 50, max 63). A typical
  step is a third of full scale.
- Autocorrelation **r = +0.27 at 300 ms, +0.00 at 600 ms** — the signal has forgotten itself within
  two samples. These are near-independent snapshots, not a sampled curve.
- But splitting the capture into even- and odd-indexed samples gives two *independent* 600 ms
  samplings of the same 57 s, each a legitimate estimate of the same true integral. They differ by
  **2.54%** (1572.5 vs 1533.1 throttle-seconds), putting the actual 300 ms estimate at **~1–2%**,
  falling as 1/√N over a longer race.

⚠️ Treat that as order-of-magnitude: it is a single realisation of the even/odd difference, from one
capture and one driving style. The naive analytic figure is far worse (±7.8%) because it estimates
a *population mean*; the integral over one specific window is the right question and the empirical
test answers it directly.

**Conclusion: cumulative fuel is viable, short-window fuel is not.** A 5 s lap is ~10 effective
samples, so a per-lap "fuel used" figure carries roughly **±26%** and would visibly jitter. See the
Throttle bullet in CLAUDE.md for the resulting design rules (integrate continuously, gate on
`Running`, keep the model in lapdata).

## HW-14: polling the Slot characteristic (2026-09-18)

No faster. Reads came back ~13/s (two 37.5 ms connection events each) with no errors, but a
read returns whichever car the powerbase's 300 ms round-robin is on, so each car still refreshed
every ~1.6–1.8 s at worst. All 12 crossings were seen by both streams, and polling saw them ~73 ms
*later* than notifications (the read round trip). Bytes 18–19 were always `0000`. The Slot value
itself only changes every 300 ms, so no client-side approach gets a crossing sooner.

## The micro-B USB port (2026-09-19)

Undocumented. On a Windows laptop it enumerates as a **CH340 USB-serial bridge** (VID `1A86`,
PID `7523`, driver `wch.cn`), i.e. a raw UART from one of the powerbase's chips. Listened
passively (DTR/RTS held low, since CH340 boards often wire those to a reset line, and nothing
written) at 9600–250000 baud, idle and for 90 s with a car lapping: **zero bytes**. Silent
at every rate means the line is idle, not a baud mismatch. Most likely a factory programming
or firmware-update line that only answers commands. Probing it means writing blind to an
undocumented MCU (risk: reset, bootloader, bricked base), so it was left there.

## 2. What we need to know

| ID | Question | Code that assumes it | If the answer differs |
|---|---|---|---|
| **HW-01** | Does the powerbase expose Slot `0x3B0B` (notify) and Command `0x3B0A` (writable)? Does its advertised name start with `Scalextric ARC`? The spec says it has two trailing spaces. | `SLOT_/COMMAND_CHARACTERISTIC_UUID`, `_name_matches()` | No Command characteristic: there's no power control on this base. Capability advertising must not claim `power_control`. Name mismatch: set `BLE_ADDRESS`, fix the filter. |
| **HW-02** | Are packets 18 bytes? How often does each car's round-robin notification come round, i.e. the worst-case reporting delay? Do timestamps stay still when no car moves? Are the last timestamps handed over on connect? | `decode_slot()`, the seeding in `handle_slot_notification()`, lapdata's `CLOCK_STEP_THRESHOLD_S`, `MINIMUM_LAP_TIME` | Changes at rest: phantom laps, and edge detection needs a rethink. The **rotation** (one packet per car ID, all 6 in turn — also note whether absent IDs are skipped) decides three things. **1)** `CLOCK_STEP_THRESHOLD_S` is a provisional 3s: set it to ~2× the worst rotation. **2)** A car's lap must take longer than one rotation, or a second same-lane crossing overwrites the first and a lap is lost — matters for sub-2s test circuits. **3)** The first lap after a connect or a timer reset can read short by up to a rotation while the clock anchor converges (a yellow flag no longer resumes from a halt, so it is no longer one of these), so `MINIMUM_LAP_TIME` (3s on the race Pi for ~5s laps) needs at least that much margin below the fastest genuine lap. |
| **HW-03** | **Power multiplier sweep.** Hold one trigger flat; the script detects that from the Throttle characteristic and steps the multiplier under you, 2s each: **100% → 75% → 50% → 0%**, then restores full power. Does the car's speed follow the multiplier, and ⚠️ **safety-critical: does `0x00` actually stop a moving car with the trigger still held?** Is the response linear (the 75/50 steps are the sweep limp mode needs)? | `command_payload()`, `FULL_POWER`, `TRACK_RACING`/`CARS_STOPPED`; the 75/50 points inform a future limp mode | ⚠️ **Car still moving at `0x00`: a yellow flag does not stop the cars, with marshals reaching onto the track.** Fall back to `PowerState(POWER_ON_TIMER_HALT, NO_POWER)` and accept that the lap spanning a yellow becomes anchored rather than an exact counter subtraction (see HW-06). This must be proven before a meet is run on BLE. Write rejected: check the response mode and pairing. **Prompt-free by design** — the operator's hands are on a controller, so the report records the objective side (the trigger really was held; the counter kept running through the 0% step, read from throttleTimestamp) and the operator reports what the car did. |
| **HW-04** | Is byte 1 the car's programmed digital ID? Does lane 1 set StartFinish1 and lane 2 set StartFinish2? Is it exactly one field per crossing, with no sensor bounce? How much jitter is there between device and wall-clock laps? | `car_timestamp.car`/`.lane`, lapdata's phantom filter | Wrong field mapping: swap `lane`. Both fields per crossing: the second must be suppressed in Layer 1. Bounce: debounce, or check `MINIMUM_LAP_TIME` covers it. |
| **HW-05** | Does power stay on indefinitely after a single write, with no keepalive? | `run()` writes only on transitions, connect and retry | Power times out: `run()`'s 1s loop must rewrite the current power state periodically. |
| **HW-06** | Does `POWER_ON_TIMER_HALT` cut power immediately? Does the powerbase clock **pause** through the halt, keep ticking, or reset? What does a car pushed over the line mid-halt report? | `_note_command_applied()` starting a new clock at the halt AND at the restart. ⚠️ **No longer the shipped yellow-flag path** — command 4 is the HW-03 fallback now, so this check matters only if that fallback is needed. | See `HALT_CLOCK_IMPACT` in the script. `kept_ticking` means the halt needs no new clock at all — and would make command 4 as good as the zero multiplier. `reset` means the backwards-detection already covers it. |
| **HW-07** | When BLE **disconnects**, what happens to track power, while halted and while racing? Are timestamps retained across a reconnect? | Connect-time write in `run()`, seeding | ⚠️ **Safety:** if a disconnect while halted restores power, a BLE drop during a yellow flag puts cars back on track with marshals out, and no software can stop it. That goes into race-day procedure. If a disconnect while racing cuts power, every car stops on a BLE drop. |
| **HW-08** | After a powerbase power-cycle, are the timers zero? Does the track have power before any app command? | Seeding, backwards reset detection | Timers not zeroed: the seeding comment is wrong. No power without the app: the base is dead until `ble` connects, which matters at meet start. |
| **HW-09** | Does command 0 (`NO_POWER_TIMER_STOPPED`) zero the Slot timestamps, with the next crossing counting from zero? | The backwards-timestamp path in `handle_slot_notification()` | Not zeroed: the "commands 0/1 zero the timers" comments are wrong. The reset path still holds for power-cycles. |
| **HW-10** | Over a long run, what is the reporting delay (median, p95, max)? How far does the powerbase clock drift, in ppm? | lapdata's running-minimum clock anchor (`ClockAnchors`) — which now only affects lap 1 and clock-spanning laps, not every lap | Large positive drift, i.e. a slow powerbase clock: the anchor can't follow it, so it needs a slow decay. Drift no longer touches ordinary laps, which are counter differences. A p95 delay near a lap time: rethink `MINIMUM_LAP_TIME`. |

| **HW-11** | Plan B for lap 1: commands 1 then 3, sent at arm. With the cars stationary, does command 1 (`NO_POWER_TIMER_TICKING`) hold them still and zero the Slot timers? Does the clock tick from command 1, or hold at zero until command 3? How long do back-to-back 1 → 3 writes take, and how soon after them is the clock's zero? (`plan_b.zero_lag_upper_bound_ms` also includes one crossing's reporting delay.) Does re-sending command 3 mid-race reset anything? | `_TIMESTAMP_BREAKING_COMMANDS` includes command 1 on the assumption it may hold at zero; if the clock ticks from command 1, move it out. Plan B itself is unbuilt — HW-12 passed, so plan A shipped. Re-sending 3 is what `handle_race_state()` and resume already do. | `not_reset`: plan B is out, and the "commands 0/1 zero the timers" comments are wrong. Cars not held: a reset at arm lets a car creep, and a jump-start hold can't use command 1. Re-sending 3 resets the clock: `ble` must stop re-sending it, or start a new clock epoch each time. |
| **HW-12** | Plan A for lap 1: is `throttleTimestamp` (Throttle `0x3B09`, bytes 7–10) a live reading of the **same** clock as the Slot timestamps? The evidence is threefold. Its anchor offset agrees with the Slot crossings' anchor. It halts on command 4 the way the Slot clock did in HW-06. It zeroes on command 1 the way the Slot timers did in HW-11. Does it also advance while the triggers are released, and how late do its notifications arrive? It also records each controller's highest throttle reading at rest (`throttle_at_rest_max`), the noise floor a jump-start threshold must sit above. | **Shipped 2026-09-20**: `BLE_CLOCK_HEARTBEAT=throttle` publishes `layer1_clock` from `handle_throttle_notification()`, on the Slot clock id. Jump-start detection will read the same throttle bytes. | `different_clock`: plan A is out; use plan B (HW-11). Same clock but not advancing at rest: no heartbeat on a stationary grid, so still plan B. |
| **HW-13** | Do the **six buttons on the powerbase itself** show up anywhere over BLE? The doc only covers controller buttons (brake `0x40`, lane change `0x80` in Throttle bytes 1–6, lane-change double-tap in byte 11). Lift cars off the track first: a base button may re-program a car's ID. | Nothing: this is to find out whether they could drive race control (e.g. start, yellow) from the base. | `visible_over_ble: false`: they can't be used from software. Otherwise `new_bytes_while_pressing` names the characteristic and byte. |
| **HW-14** | Does **reading** Slot (it is readable, HW-01) see crossings sooner than its 300 ms round-robin notifications? Does each read return the next car ID, or repeat the last notification? What are the two undocumented bytes 18–19? Drive car 5 in steady laps for 30 s. | Nothing yet: lap *position* needs to reach the leaderboard fast; last-lap times can wait ~1 s. | `polling_earlier_ms` median well above 300: add a polling mode to `ble_to_timestamps`. About 0, or reads repeat the notified car: the 1.8 s rotation stands. |

Not tested, because it isn't practical: the uint32 tick counter wrapping after
~497 days of uptime. Unit tests already cover it as a timer reset.

## 3. Full-stack checks

These run with the real stack on the Pi (`./deploy/deploy.ps1`, BLE Layer 1) and a staged
race. They're manual, because the thing being judged is a physical track. Watch `docker
logs -f ble` in one terminal. To see race state:
`docker exec mosquitto mosquitto_sub -t race_state | jq -c '{state, yellow_seconds_left}'`

| ID | Do | Expect |
|---|---|---|
| **E1** Laps | Start a race from `/racecontrol`, drive 5 laps, time one lap with a stopwatch. | One lap counted per crossing, lap times within a few hundredths of the stopwatch, no phantom laps at lights out. |
| **E2** Yellow flag | Mid-race, press Yellow Flag, and keep driving through the grace. | Leaderboard shows "Yellow Flag - 5s" counting down; cars keep running for the grace **and their laps keep counting**; at 0 `ble` logs `Command characteristic <- 3 at power 0x00` and the cars stop. |
| **E3** Resume after a cut | Wait ~20s, press Resume Race, drive 3 laps. | `ble` logs **no new clock** at either the cut or the resume (the counter never stopped); cars move again; the lap times after resume are sane. That's review item 1, proven on hardware. |
| **E4** Resume Now | Yellow Flag, then Resume Now within the grace period. | Power never cuts; the race stays Running. |
| **E5** `ble` restart while Paused | Let a yellow flag stop the cars, then `docker restart ble`. | After reconnect, `ble` logs `Command characteristic <- 3 at power 0x00` and the cars **stay stopped** (the track stays energised — that is expected). That's review item 2, proven on hardware. |
| **E6** Powerbase drop while Paused | Let a yellow flag stop the cars, switch the powerbase off and on (or walk the Pi out of range). | Same as E5 once reconnected. **Also note** whether the cars moved again while disconnected (see HW-07). |
| **E7** `ble` restart mid-race | While Running, `docker restart ble`, keep driving. | No phantom laps on reconnect (seeding); laps continue counting. |
| **E8** End during yellow | Yellow Flag, then End Race during the grace period. | Race Finished; power on (`<- 3`); no later power cut. |
| **E9** Lap 1 | Set the meeting's start grid to **in front of the line** (first crossing counts). Start a race and stopwatch from lights-out to the first crossing. Then set the grid **behind** the line and repeat, stopwatching lights-out to the **second** crossing (the first is a discarded part-lap). | Lap 1 within a few hundredths of the stopwatch **both times**. Lap 1 is timed from lights-out whatever the grid, so `driver_lap` shows `"timing":"from_go"` for it in both cases and `"counter"` for every lap after. This is the one lap per race that depends on the clock anchor, so it is also the check that proves the `layer1_clock` heartbeat is working on real hardware. |
| **E10** No clock change at a yellow | Yellow Flag, let the grace expire, then Resume Race. | ⚠️ `ble` logs **no new clock at all** — stopping the cars with a zero multiplier leaves the counter running, which is the whole point. The lap spanning the stoppage shows `"timing":"counter"` (an exact subtraction, not `anchored`) and *includes* the stopped time, so it is far too slow to be a fastest lap. Laps after the resume are `counter` and sane. |
| **E12** Physical power cycle mid-race | ⚠️ **Press Yellow Flag or Pause first** (see the warning below), then switch the powerbase off at the mains mid-race, wait ~30s as if clearing a track short, switch it back on and resume. Drive 3 more laps. | No phantom laps on reconnect, **and no lost ones**: a car that crossed once during the outage has that lap published when we reconnect (a car that crossed twice still loses one — the powerbase keeps only its most recent stamp). `ble` logs a **new clock** at the reconnect, so no lap is timed across the reset. The lap spanning the outage is long — roughly the whole outage — and its `driver_lap` says `"timing":"anchored"` (or `"arrival"` if its packet beat the first heartbeat on the new clock). ⚠️ **No lap time is ever negative or absurdly short**: the powerbase zeroes its timers, so the counter after the cycle is smaller than the one before it, and only the clock change stops that becoming a negative subtraction. Laps after the resume are `counter` again and sane. Lap counts continue from where they were. |
| **E11** GPIO fallback | Redeploy with `./deploy/deploy.ps1 -Layer1 gpio`, drive 3 laps. | Laps count, and `car_timestamp` carries `counter_ms` + a `gpio:<boot id>` clock. ⚠️ An old `gpio` image publishes the removed `timestamp` field, which lapdata now **drops outright** — logging "a Layer 1 image is older than lapdata" and counting nothing. There is no fallback by design, so this check is what proves the fallback is actually deployable. |

⚠️ **Pause before power-cycling the powerbase mid-race.** On every BLE connect `ble`
writes the power state the race calls for, so if the race is still `Running` when the base
comes back, **power is restored the instant BLE reconnects** — while you may still be
leaning over the track. Pausing first (or a yellow flag that has expired) means the
connect-time write is `CARS_STOPPED` instead, and the cars stay put until you resume. Same
reasoning as HW-07, but triggered by the operator rather than by a dropped link.

## 4. Report back

Bring `hw-report.json` and the E1–E11 results to the next session. Then:
- Fix any `fail`s.
- Make the `code_impact` notes from `review` checks into code or race-day procedure.
- Update the simulated behaviour in `docs/mocked-ble-plan.md`, so the dev mock copies the real hardware rather than today's assumptions.
- Record HW-11 and HW-12's conclusions in `docs/lap-timing-plan.md`, which picks plan A or plan B for lap 1 from them.
