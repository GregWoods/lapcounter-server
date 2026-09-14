# BLE Layer 1: hardware validation

`ble` is the live Layer 1 but has never run against a real Scalextric ARC Pro powerbase.
The unit tests prove the code does what it *intends*; they can't prove the powerbase
behaves the way the code *assumes*. This file lists exactly those assumptions, and
`hardware_check.py` tests each one against the hardware.

**Do this before the first meet on BLE.** HW-06 and HW-07 matter most: they decide
whether yellow-flag power cuts keep lap times right and whether they're safe.

## 1. Run the scripted checks

Takes about 20 minutes. You need one car per controller, and ideally a stopwatch. Never
run it during a race: it cuts track power, and HW-09 zeroes the lap timers.

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
The report is rewritten after every check, so an aborted run keeps its results. Each
check ends with a verdict:
- `pass`: the hardware matches the code.
- `fail`: it doesn't.
- `review`: the answer changes code or race-day procedure; see `code_impact` in the report.
- `info`: a measurement, not a yes/no.

## 2. What we need to know

| ID | Question | Code that assumes it | If the answer differs |
|---|---|---|---|
| **HW-01** | Does the powerbase expose Slot `0x3B0B` (notify) and Command `0x3B0A` (writable)? Does its advertised name start with `Scalextric ARC`? The spec says it has two trailing spaces. | `SLOT_/COMMAND_CHARACTERISTIC_UUID`, `_name_matches()` | No Command characteristic: there's no power control on this base. Capability advertising must not claim `power_control`. Name mismatch: set `BLE_ADDRESS`, fix the filter. |
| **HW-02** | Are packets 18 bytes? How often does each car's round-robin notification come round, i.e. the worst-case reporting delay? Do timestamps stay still when no car moves? Are the last timestamps handed over on connect? | `decode_slot()`, the seeding in `handle_slot_notification()`, `CLOCK_STEP_THRESHOLD_S`, `MINIMUM_LAP_TIME` | Changes at rest: phantom laps, and edge detection needs a rethink. The **rotation** (one packet per car ID, all 6 in turn — also note whether absent IDs are skipped) decides three things. **1)** `CLOCK_STEP_THRESHOLD_S` is a provisional 3s: set it to ~2× the worst rotation. **2)** A car's lap must take longer than one rotation, or a second same-lane crossing overwrites the first and a lap is lost — matters for sub-2s test circuits. **3)** The first lap after a connect, timer reset or halt resume (every yellow flag) can read short by up to a rotation while the clock anchor converges, so `MINIMUM_LAP_TIME` (3s on the race Pi for ~5s laps) needs at least that much margin below the fastest genuine lap. |
| **HW-03** | Is a 20-byte `POWER_ON_RACING` write accepted, and do cars get full throttle with the multiplier bytes at `0x3F`? | `command_payload()`, `FULL_POWER` | Write rejected: check the response mode and pairing. Cars slow or dead: the multiplier semantics are wrong. |
| **HW-04** | Is byte 1 the car's programmed digital ID? Does lane 1 set StartFinish1 and lane 2 set StartFinish2? Is it exactly one field per crossing, with no sensor bounce? How much jitter is there between device and wall-clock laps? | `car_timestamp.car`/`.lane`, lapdata's phantom filter | Wrong field mapping: swap `lane`. Both fields per crossing: the second must be suppressed in Layer 1. Bounce: debounce, or check `MINIMUM_LAP_TIME` covers it. |
| **HW-05** | Does power stay on indefinitely after a single write, with no keepalive? | `run()` writes only on transitions, connect and retry | Power times out: `run()`'s 1s loop must rewrite the current power state periodically. |
| **HW-06** | Does `POWER_ON_TIMER_HALT` cut power immediately? Does the powerbase clock **pause** through the halt, keep ticking, or reset? What does a car pushed over the line mid-halt report? | `_note_command_applied()` re-anchoring, yellow-flag grace expiry | See `HALT_CLOCK_IMPACT` in the script. `kept_ticking` means the re-anchor can go. `reset` means the backwards-detection already covers it. No power cut means yellow flags don't stop cars at all. |
| **HW-07** | When BLE **disconnects**, what happens to track power, while halted and while racing? Are timestamps retained across a reconnect? | Connect-time write in `run()`, seeding | ⚠️ **Safety:** if a disconnect while halted restores power, a BLE drop during a yellow flag puts cars back on track with marshals out, and no software can stop it. That goes into race-day procedure. If a disconnect while racing cuts power, every car stops on a BLE drop. |
| **HW-08** | After a powerbase power-cycle, are the timers zero? Does the track have power before any app command? | Seeding, backwards reset detection | Timers not zeroed: the seeding comment is wrong. No power without the app: the base is dead until `ble` connects, which matters at meet start. |
| **HW-09** | Does command 0 (`NO_POWER_TIMER_STOPPED`) zero the Slot timestamps, with the next crossing counting from zero? | The backwards-timestamp path in `handle_slot_notification()` | Not zeroed: the "commands 0/1 zero the timers" comments are wrong. The reset path still holds for power-cycles. |
| **HW-10** | Over a long run, what is the reporting delay (median, p95, max)? How far does the powerbase clock drift, in ppm? | Running-minimum clock anchor, lapdata's 30s `HW_TIMESTAMP_TOLERANCE_NS` | Large positive drift, i.e. a slow powerbase clock: the anchor can't follow it, so it needs a slow decay. A p95 delay near a lap time: rethink `MINIMUM_LAP_TIME`. |

Not tested, because it isn't practical: the uint32 millisecond counter wrapping after
~49.7 days of uptime. Unit tests already cover it as a timer reset.

## 3. Full-stack checks

These run with the real stack on the Pi (`./deploy/deploy.ps1`, BLE Layer 1) and a staged
race. They're manual, because the thing being judged is a physical track. Watch `docker
logs -f ble` in one terminal. To see race state:
`docker exec mosquitto mosquitto_sub -t race_state | jq -c '{state, yellow_seconds_left}'`

| ID | Do | Expect |
|---|---|---|
| **E1** Laps | Start a race from `/racecontrol`, drive 5 laps, time one lap with a stopwatch. | One lap counted per crossing, lap times within a few hundredths of the stopwatch, no phantom laps at lights out. |
| **E2** Yellow flag | Mid-race, press Yellow Flag. | Leaderboard shows "Yellow Flag - 5s" counting down; power **stays on** for the grace; `ble` logs `Command characteristic <- 4` at 0 and cars stop. |
| **E3** Resume after a cut | Wait ~20s, press Resume Race, drive 3 laps. | `ble` logs `re-anchoring the clock offset`; power returns; the lap times after resume are sane. That's review item 1, proven on hardware. |
| **E4** Resume Now | Yellow Flag, then Resume Now within the grace period. | Power never cuts; the race stays Running. |
| **E5** `ble` restart while Paused | Let a yellow flag cut power, then `docker restart ble`. | After reconnect, `ble` logs `Command characteristic <- 4` and the track **stays unpowered**. That's review item 2, proven on hardware. |
| **E6** Powerbase drop while Paused | Let a yellow flag cut power, switch the powerbase off and on (or walk the Pi out of range). | Same as E5 once reconnected. **Also note** whether power came back while disconnected (see HW-07). |
| **E7** `ble` restart mid-race | While Running, `docker restart ble`, keep driving. | No phantom laps on reconnect (seeding); laps continue counting. |
| **E8** End during yellow | Yellow Flag, then End Race during the grace period. | Race Finished; power on (`<- 3`); no later power cut. |

## 4. Report back

Bring `hw-report.json` and the E1–E8 results to the next session. Then:
- Fix any `fail`s.
- Make the `code_impact` notes from `review` checks into code or race-day procedure.
- Update the simulated behaviour in `docs/mocked-ble-plan.md`, so the dev mock copies the real hardware rather than today's assumptions.
