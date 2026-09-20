# Plan: per-car power capping

**Status:** proposal, 2026-09-20. Nothing implemented. Depends on Layer 1 capability
advertising (see "Prerequisite" below), which is also unimplemented.

The Command characteristic's per-car power bytes (`0x3B0A` bytes 1–6, `0…0x3f`) are
already load-bearing in this project: `FULL_POWER`/`NO_POWER` is how `CARS_STOPPED` stops
the cars at a yellow flag, confirmed on real hardware in HW-03. Everything below is the
same byte at intermediate values, **per car** instead of the same value for all six.

Two uses, both operator-facing:

1. **Virtual safety car** — cars keep circulating slowly instead of stopping dead.
2. **Per-driver power cap** — a lower maximum for younger or less experienced drivers.

**Not in scope: the ghost car** (the `+0x80` "app drives this car directly" bit). The
protocol supports it and 3 Hz would be plenty of update rate, but this hardware gives no
position feedback at all — the only position signal is a start/finish crossing, once per
lap, reaching us up to ~1.8 s late through the Slot round-robin. So an app-driven car must
run open-loop below the slowest corner's de-slot threshold everywhere, including the
straights, and a de-slot is undetectable (`0x3B0C` reports overcurrent/undervoltage, not a
car off the track). That makes it a rolling obstacle, not a competitor. Parked
deliberately; revisit only if position sensing ever appears.

## Why this is cheap

The write path exists. `command_payload()` already sends the 20-byte Command write and
`PowerState` already pairs a state byte with a power multiplier. Three things change:

- `PowerState.power` becomes a **per-car vector** rather than one scalar applied to all six.
- `race_state` gains a top-level per-car power field, so lapdata can drive it.
- Both features need `layer1_status` capability advertising first.

⚠️ **Neither feature writes continuously.** Both stay edge-triggered like today's power
writes — a cap changes at a race transition or a lineup change, not per tick. The
sustained-write regime a ghost car would need (and its untested effect on the powerbase)
is not entered here.

⚠️ **No clock impact whatsoever.** Everything here is command 3 at a varying multiplier,
exactly as `CARS_STOPPED` already is, so the powerbase counter never stops and no new
clock is started. This is the whole reason the zero-multiplier approach was chosen over
the halting commands (see CLAUDE.md, "Yellow flags"); intermediate values inherit it free.

## Ownership: lapdata decides, BLE writes

Same split as the fuel model. `ble` sees only car IDs 1–6 and must stay dumb — it knows
nothing about drivers, sessions or handicaps and cannot, so all policy lives in lapdata,
which has the lineup. Changing a handicap rule then never touches the BLE container.

lapdata's `lane` **is** the powerbase's digital car ID (1–6), so the mapping is direct.

### Transport: a top-level `car_power` in `race_state`

`ble` already subscribes to `race_state` for its power writes, so it needs no new
subscription:

```json
"car_power": [100, 100, 60, 100, 100, 100]
```

Six entries, indexed by car ID 1–6, **percent of full power (0–100)**, always present and
complete — including empty lanes, which get 100.

Three reasons for top-level rather than a field on each `drivers[]` entry:

- The FastestLap serialisation's `session_drivers[]` is not lane-indexed and its `lane`
  is `None` for drivers not in the current race. A top-level array works for both
  serialisations unchanged.
- `ble` should not have to parse driver records to find a byte.
- It must cover all six IDs, including lanes with no driver.

**Percent, not the raw byte.** Layers 2+ must not carry hardware units; `ble` converts
percent → `0…0x3f` in the one place that unit already lives, next to `DEVICE_TICK_S`.
That also keeps the Admin form honest on a GPIO meet, where the number means nothing.

### Precedence: one resolved value, computed in one place

The Command write carries one byte per car, so these cannot be layered as separate
writes — lapdata resolves them to a single value. **Most restrictive wins:**

```
car_power[car] = 0                               if state == 'Paused'
                 else min(driver_cap[car], safety_car_cap_if_active)
```

⚠️ **A driver cap must never be able to raise a stopped car off zero.** `min()` with a
floor of 0 guarantees it; do not implement this as "apply the cap unless paused", which
inverts under any future state that also stops the cars.

⚠️ **Connect-time writes must carry the vector too.** `run()` already writes
`_command_for_race_state(_last_seen_race_state)` on every BLE connect, precisely so a
reconnect during `Paused` doesn't set cars moving with marshals on track. That rule
extends unchanged: a reconnect during a safety car must restore the safety-car vector,
not blanket full power.

## Feature 1: virtual safety car

### Yellow flag and safety car are two different operator intents

Today's yellow flag exists for **marshal access**: grace period at full power, then the
cars stop dead so someone can reach onto the track. A safety car is for incidents a driver
can recover from themselves, or debris — **nobody goes on the track**, and the cars keep
circulating slowly so the race isn't killed.

⚠️ **Do not make this one setting on the existing button.** "Cars still moving" is exactly
the wrong outcome if the operator pressed yellow because someone is about to reach onto
the track. Two buttons in RaceControl:

| Button | Grace | Then | For |
|---|---|---|---|
| **Yellow Flag** (existing, unchanged) | full power for `yellow_grace_seconds` | `Paused` — cars stop | marshal access |
| **Safety Car** (new) | full power for `yellow_grace_seconds` | `SafetyCar` — cars capped | self-recoverable incident, debris |

Both share the existing grace machinery: `race_control` `safety_car` enters the same
`Yellow` state, and lapdata's grace timer transitions to `SafetyCar` instead of `Paused`.
The generation-number discipline every lapdata timer already uses applies identically.

"Include the grace period or not" then falls out as a per-button answer rather than a
setting: the grace is what lets the rest of the field get clear of the incident, and it
is as useful before a slowdown as before a stop. If a "slow down *now*" variant is ever
wanted, it is `yellow_grace_seconds = 0` for that action, not a separate mechanism.

### Laps count under a safety car

`SafetyCar` joins `COUNTING_STATES` alongside `Running` and `Yellow`. The cars are moving
and still racing, so a crossing is a real lap — the same argument that put `Yellow` in
there on 2026-09-20. This matches real racing, where laps count behind the safety car.

Consequences to handle:

- A race can **finish** under a safety car, like it already can under `Yellow`.
  `_check_race_end()` needs the same clearing treatment.
- FastestLap sessions are ranked on personal best, so a slow safety-car lap is harmless —
  it can never be a PB. No special casing needed.
- The lap spanning the slowdown is one long, **exactly measured** lap. The car really was
  slow for part of it. Expected and correct, same as the yellow-flag stop today.

### Config

`sessions.safety_car_power` — nullable INT, percent. `None` = the Safety Car button is
hidden. Sits next to `yellow_grace_seconds` in the Admin session form. Needs a migration
(`004-...`, after the unimplemented 003) and `schema.sql` kept in step — remember that a
missing column takes out *all* of that table's endpoints, not just this feature.

Cleared by the operator only: "Resume Race" from `SafetyCar`, same as from `Paused`. No
auto-resume.

## Feature 2: per-driver power cap

A lower maximum for younger drivers, so they can use the full trigger range without the
car being uncontrollably fast.

### Where the setting lives: on the driver

`drivers.max_power` — nullable INT, percent, `None` = full. Edited in the Admin driver
form.

Global rather than per-session, because unlike the fuel handicap this is a property of the
person: a nine-year-old is nine years old in every session of the meeting. If a per-session
override is ever wanted, `session_drivers` already exists for exactly that shape.

### It changes results, so it must be visible and recorded

⚠️ A silent handicap that alters finishing order is worse than no handicap. Two
consequences:

- The leaderboard and NextRace should mark a capped driver. Wording should say what it is
  (e.g. "75%"), not imply a disadvantage.
- `driver_races` should record the cap in force for that race, so a result can be re-read
  after the meet. Cheap to add now, impossible to reconstruct later.

### ⚠️ A cap is not a proportional speed reduction

HW-03 measured four coarse points on one car (`0x3f` ran, `0x2f` slower, `0x20` slower
again, `0x00` stopped). The response is known to be non-linear and untuned, and it will
differ per car and with track voltage. So "75%" is a **nominal** setting, not a promise
about speed, and the Admin form should be worded accordingly until a calibration sweep
exists.

**The throttle profile characteristic is probably the better mechanism for this one.**
`0xFF01`–`0xFF06` write a 64-entry throttle→power curve per car. Scaling the multiplier
flattens the top of the trigger travel — the last third of the pull does nothing —
whereas reshaping the curve keeps the whole trigger range usable at reduced pace, which
is exactly what a young driver wants. Recommend shipping the multiplier version first
(it reuses everything above) and treating the profile version as the refinement, since it
needs a per-car write, a profile to restore on release, and its own hardware validation.

⚠️ **A cap can be too low to move the car at all.** Static friction from a standstill is
higher than what sustains motion, so a value that keeps a rolling car going may leave it
stuck on the grid or stalled out of a corner. The minimum usable value has to be measured
before the Admin form decides its floor — a cap that strands a child's car on the grid is
a worse outcome than no cap.

## Prerequisite: Layer 1 capability advertising

Both features are **case 3** from CLAUDE.md's "Layer 1 capability advertising" — operator
settings that only work on one Layer 1. Under GPIO there is no power control at all, so
`safety_car_power` and `max_power` would save happily and silently do nothing, and a
Safety Car button would produce a race that never slows down. That is config that lies,
and presence-of-topic cannot answer it because the settings must resolve before any data
flows.

So `layer1_status` (retained, `capabilities: [...]`, published by whichever Layer 1 is
running) ships first. The Admin forms disable both settings with *"requires ARC
powerbase"* when `power_control` is absent, and RaceControl hides the Safety Car button.
⚠️ Branch on the **capability**, never on the `layer1` name.

## Hardware validation still needed

HW-03 proved the two safety-critical halves (a zero multiplier stops a car; the counter
keeps running through it). Capping needs more than four points:

- **A finer sweep, on more than one car.** Enough points to know whether percent→byte
  should be linear or curved, and how much cars differ from each other.
- **The minimum usable multiplier**, from a standstill and out of a corner — the floor for
  both features' Admin forms.
- **A sensible safety-car value.** Slow enough to be obviously a slowdown, fast enough that
  cars don't stall on the tightest corner.

These extend the existing HW-03 sweep rather than needing new machinery; `hardware_check.py`
already steps the multiplier under a held trigger and reads the counter through it.

## Open questions

1. **Does the safety car cap all cars equally, or hold station?** Equal capping is trivial
   and is what this plan assumes. Actual station-holding needs position feedback, which
   this hardware does not have (see the ghost-car reasoning above).
2. **Does a driver cap apply during a safety car, or is the safety-car value absolute?**
   `min()` says the cap still applies, so a capped driver is slower still. Probably right,
   but it means a young driver drops further back under every safety car.
3. **Percent or a named level?** "75%" is honest about being nominal; "Novice / Junior /
   Full" hides the non-linearity behind a label the operator can't misread. The named
   version may survive contact with a real meet better.
4. **Should `max_power` follow the driver or the car?** A slower *car* is the other way to
   handicap, and `cars` is already where tank size and consumption rate are proposed to
   live for fuel. Driver is recommended here because the reason is the driver's age.
