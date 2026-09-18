# Plan: mocked BLE Layer 1 for local dev

**Status:** steps 1–3 done (2026-09-13): `ble/mock_powerbase.py`, `ble/mock_bleak.py`,
`ble/mock_ble_to_timestamps.py`, the `mocked-ble` compose profile, and
`ble/test_mock_powerbase.py` / `ble/test_mock_bleak.py`. Verified live against the dev
stack: laps reach lapdata, no phantom laps on connect, `pause` cuts power (command 4) and
`resume` re-anchors, and the double Layer 1 guard fires when `mocked-gpio` also runs.
Steps 4–5 done the same day: `ble/test_mock_scenarios.py` (halt/resume stamps checked
against the simulator's ground truth, reconnect while Paused with a power-restoring drop,
a failed halt retried, a retry writing the current state rather than a stale halt), and
CLAUDE.md. Only step 6 remains, after the hardware run.

Decisions: `mocked-ble` **is now the dev default**; `mocked-gpio` sits behind
`--profile mocked-gpio`, and lapdata's `depends_on` names no Layer 1. Also no throttle
simulation, no UI badge. `ble/.dockerignore` keeps the mocks, tests and docs out of the
production image (the dev volume mount supplies them).

Deviations from the plan below:
- The Slot round-robin covers all 6 IDs whatever `MOCK_CARS` is (tagged HW-02), so the
  reporting delay stays hardware-like with fewer cars.
- Cars move only under command 3. Whether command 2 follows the throttle isn't
  documented, and ble never sends it.
- `mock/powerbase` also carries `connected` and `timestamps_ticking`.
- `power_cycle()` exists and is tested, but nothing triggers it from the running container yet.

## Why

In dev, `mocked-gpio` publishes `car_timestamp` directly. That tests lapdata and React
but none of `ble/ble_to_timestamps.py`, which is where today's bugs were:
- clock anchoring across a halt;
- the power state written on connect;
- seeding on reconnect;
- retrying a failed write.

Dev also has no way to *see* power control. A yellow-flag cut is invisible without a
track. The goal is to run the **production BLE code, unmodified**, against a simulated
powerbase, with no Bluetooth adapter.

## Approach: fake the BLE link, not MQTT

`ble_to_timestamps.py` resolves the names `BleakClient` and `BleakScanner` at call
time, inside `find_device_address()` and `run()`. A dev-only entrypoint can swap in
fakes and then run the real `run()`. Everything above the BLE link is then real code:
- decoding;
- seeding and anchoring;
- command writes and the halt re-anchor;
- the connect-time power state and retries;
- the MQTT side.

A second MQTT-level mock in the style of `mocked-gpio` was rejected. It would copy that
logic instead of exercising it, and the copy would pass while the real code failed.

## Components

### 1. `ble/mock_powerbase.py`: `SimulatedPowerbase`

A pure simulation with an injectable clock, so tests can run it faster than real time.

- **Device clock** in 10 ms ticks (the protocol doc says ms; the hardware disagrees, see `TICK_S`), driven by the Command state machine:

  | Command | Track power | Timestamps |
  |---|---|---|
  | 0 | off | zeroed, stopped |
  | 1 | on, speed 0 | zeroed, ticking |
  | 2 | on | halted |
  | 3 | on, follows throttle × multiplier | ticking |
  | 4 | off | halted |

  Each behaviour cites the hardware check it depends on (e.g. `# HW-06: clock pauses
  through a halt`), so the simulation gets corrected when `hw-report.json` comes back.
- **Cars:** `MOCK_CARS` (default 6) cars. Lap-time model borrowed from
  `gpio/mocked_timestamps.py` (base + ability + outliers). Each car has a lane, with
  optional random lane changes. A car advances round the lap only while its multiplier
  is > 0 and track power is on. On reaching the line it stamps the device clock into
  StartFinish[lane].
- **Multiplier bytes:** parsed from each write. All-zero bytes 1–6 make cars stop *and*
  log a warning, reproducing the "these bytes aren't padding" trap.
- **Slot notifications:** one car per `MOCK_SLOT_INTERVAL_MS` (default 50ms, so a 300ms
  cycle), round-robin, encoded as the real 18-byte packet (sequence, car ID,
  StartFinish1/2, pitlane zeros). A crossing is therefore reported 0–300ms late, which
  exercises the anchoring.
- **Startup state:** non-zero retained timestamps by default, so every connect exercises
  seeding.
- **Behaviour on disconnect:** `MOCK_DISCONNECT_POWER=hold|off|on`, default `hold`, the
  current assumption. Unknown until HW-07.
- **Power-cycle:** zeroes the timers (HW-08).

### 2. `ble/mock_bleak.py`: fake bleak surface

Only the parts `ble_to_timestamps.py` uses.

- **`FakeBleakScanner.find_device_by_filter`** returns a device named `"Scalextric ARC  "`,
  with the two trailing spaces, so `_name_matches()` is exercised.
- **`FakeBleakClient`:**
  - async context manager with `is_connected`;
  - `start_notify(uuid, callback)` runs a pump task on the running loop, calling
    back on the same thread as real bleak;
  - `write_gatt_char(uuid, payload)` applies the command to the powerbase.
- **Fault injection:**
  - `MOCK_DROP_EVERY_S`: periodic disconnects;
  - `MOCK_WRITE_FAIL_RATE`: tests the retry;
  - `MOCK_NO_COMMAND_CHARACTERISTIC`: ARC One, every write rejected.

### 3. `ble/mock_ble_to_timestamps.py`: entrypoint

```python
import ble_to_timestamps as ble
from mock_bleak import FakeBleakClient, FakeBleakScanner
ble.BleakClient, ble.BleakScanner = FakeBleakClient, FakeBleakScanner
# then the same body as ble_to_timestamps' __main__ block
```

`ble_to_timestamps.py` itself gets no mock hooks.

### 4. Observability (dev only)

- **`mock/powerbase` topic:** retained, published on each change and at 1Hz, carrying
  `{command, track_power, device_ms, cars: [{car, lane, laps, moving}]}`. Watch it with
  `docker exec mosquitto mosquitto_sub -t mock/powerbase`. Nothing in lapdata, React or
  the API may subscribe to it; it is not part of the contract.
- **Double Layer 1 guard:** the mock also subscribes to `car_timestamp` and logs an ERROR
  if it sees payloads it didn't publish. That means `mocked-gpio` is running too, and
  every lap is being double-counted.

### 5. Compose (`compose.dev.yaml`)

```yaml
mocked-ble:
  profiles: ["mocked-ble"]
  container_name: mocked-ble
  build: ./ble
  command: ["python", "mock_ble_to_timestamps.py"]
  volumes:
    - ./ble:/app              # edit live; restart like lapdata (no hot reload)
  environment:
    - MQTT_HOSTNAME=mosquitto
    - MOCK_CARS=6
  depends_on: [mosquitto]
```

No D-Bus mount or `NET_ADMIN`. The same one-Layer-1 trap applies as for `ble`:
```
docker compose -f compose.dev.yaml stop mocked-gpio
docker compose -f compose.dev.yaml --profile mocked-ble up -d mocked-ble
```

### 6. Tests (`ble/`, run by the root pytest)

- **`test_mock_powerbase.py`**, with a fake clock:
  - command 4 freezes the clock and stops cars;
  - command 0 zeroes the timers;
  - zero multiplier bytes stop cars;
  - packets round-trip through `ble.decode_slot()`.
- **`test_mock_scenarios.py`**, running the real `ble.run()` against the fakes for a few
  seconds with short laps:
  - lap deltas stay right across a halt and resume (review item 1, end to end);
  - a reconnect while `race_state` is `Paused` writes command 4 (review item 2);
  - an injected write failure is retried with the current state.

## Order of work

1. `SimulatedPowerbase` + its tests. Most of the effort.
2. Fake bleak + entrypoint; run it locally against mosquitto.
3. Compose service + `mock/powerbase` topic + double Layer 1 guard.
4. Scenario tests against the real `run()`.
5. CLAUDE.md: add `mocked-ble` to the Layer 1 table and dev commands.
6. After the hardware run: update the simulated behaviours from `hw-report.json`.

Roughly one focused session for 1–3, and a second for 4–6.

## Decisions for Greg before starting

1. **Which mock is the dev default?** `mocked-ble` exercises more of the real system and
   is what the Pi runs. Making it the default means putting `mocked-gpio` behind a
   profile and changing lapdata's `depends_on`. Recommended once step 4 passes.
2. **Throttle characteristic (`0x3B09`)?** Simulating it now would help the future fuel
   feature. Recommended: not yet, until fuel work starts.
3. **UI for the mock's power state?** A dev-only badge in RaceControl showing
   `mock/powerbase`. Recommended: no, `mosquitto_sub` is enough, and a UI subscriber is
   the first step towards layers 2+ knowing about the hardware.
