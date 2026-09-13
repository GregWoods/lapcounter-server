"""Hardware validation for the BLE Layer 1.

Answers the questions in HARDWARE_VALIDATION.md against a real Scalextric ARC Pro
powerbase: everything ble_to_timestamps.py assumes about the hardware that unit tests
can't prove. Each check has an ID (HW-01...), prompts the operator where a human has to
drive a car or look at the track, and writes what it observed to a JSON report. The
analysis is pure functions, covered by test_hardware_check.py. Packet decoding and the
Command payload are imported from ble_to_timestamps, so it is the production code's
view of the hardware that gets checked.

⚠️ Stop the ble container first (the powerbase takes one BLE connection at a time), and
never run this during a race: it cuts track power, and HW-09 zeroes the lap timers.

On the Pi (the script is in the ble image from the next build-and-push-ble.ps1):
  docker stop ble
  docker run --rm -it -v /var/run/dbus:/var/run/dbus --cap-add NET_ADMIN -v "$PWD:/out" \\
      gregkwoods/lapcounter-server-ble:latest python hardware_check.py --report /out/hw-report.json
  docker start ble

On any machine with Bluetooth, from the repo root:
  pip install bleak paho-mqtt
  python ble/hardware_check.py

Run a subset with --only HW-06,HW-07. The report is rewritten after every check, so an
aborted run keeps what it had found.
"""
import argparse
import asyncio
import json
import os
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner

import ble_to_timestamps as ble

THROTTLE_CHARACTERISTIC_UUID = "00003b09-0000-1000-8000-00805f9b34fb"
TRACK_CHARACTERISTIC_UUID = "00003b0c-0000-1000-8000-00805f9b34fb"

# Long enough that "clock paused through the halt" and "clock kept ticking" differ by far
# more than a round-robin reporting delay.
HALT_TEST_SECONDS = 15


@dataclass(frozen=True)
class SlotSample:
    arrival: float      # unix seconds on this machine
    car: int
    t1: int             # StartFinish1, powerbase ms
    t2: int             # StartFinish2, powerbase ms


@dataclass(frozen=True)
class Crossing:
    arrival: float
    car: int
    lane: int           # which StartFinish field changed
    device_ms: int


# --------------------------------------------------------------------- analysis (pure)

def verdict(ok: bool | None) -> str:
    return 'skipped' if ok is None else ('pass' if ok else 'fail')


def find_crossings(samples: list[SlotSample], after: float = float('-inf')) -> list[Crossing]:
    """Edge-detect crossings the way ble_to_timestamps does: per car, a non-zero
    StartFinish field that differs from that car's previous packet, with each car's
    first packet only seeding. Every sample seeds, but only crossings arriving after
    `after` are returned."""
    previous: dict[int, tuple[int, int]] = {}
    found = []
    for s in samples:
        before = previous.get(s.car)
        previous[s.car] = (s.t1, s.t2)
        if before is None or s.arrival <= after:
            continue
        for lane, now, was in ((1, s.t1, before[0]), (2, s.t2, before[1])):
            if now and now != was:
                found.append(Crossing(s.arrival, s.car, lane, now))
    return found


def notification_intervals(samples: list[SlotSample]) -> dict:
    """Per car, how often the round-robin Slot notification comes round. The gap is the
    worst-case delay between a crossing and hearing about it."""
    arrivals: dict[int, list[float]] = {}
    for s in samples:
        arrivals.setdefault(s.car, []).append(s.arrival)
    result = {}
    for car, times in sorted(arrivals.items()):
        gaps = [b - a for a, b in zip(times, times[1:])]
        result[car] = {
            'packets': len(times),
            'median_gap_ms': round(statistics.median(gaps) * 1000) if gaps else None,
            'max_gap_ms': round(max(gaps) * 1000) if gaps else None,
        }
    return result


def reporting_lateness(crossings: list[Crossing]) -> dict | None:
    """How late each crossing was reported, relative to the least-delayed one: the same
    running-minimum anchor ble_to_timestamps uses. Only meaningful over a stretch with
    no halt or timer reset in it."""
    if len(crossings) < 2:
        return None
    offsets = [c.arrival - c.device_ms / 1000 for c in crossings]
    anchor = min(offsets)
    late_ms = sorted((o - anchor) * 1000 for o in offsets)
    return {
        'crossings': len(late_ms),
        'median_ms': round(statistics.median(late_ms)),
        'p95_ms': round(late_ms[min(len(late_ms) - 1, int(len(late_ms) * 0.95))]),
        'max_ms': round(late_ms[-1]),
    }


def lap_deltas(crossings: list[Crossing]) -> list[dict]:
    """Consecutive crossings by the same car: the lap on the powerbase clock against the
    lap on ours. The difference is the reporting jitter device timestamps keep out."""
    deltas = []
    for a, b in zip(crossings, crossings[1:]):
        if a.car == b.car:
            device_s = (b.device_ms - a.device_ms) / 1000
            wall_s = b.arrival - a.arrival
            deltas.append({'device_s': round(device_s, 3), 'wall_s': round(wall_s, 3),
                           'jitter_ms': round((wall_s - device_s) * 1000)})
    return deltas


def double_triggers(crossings: list[Crossing], within_s: float = 1.0) -> list[dict]:
    """Same car, same sensor, closer together than any real lap: a sensor bounce the
    powerbase didn't debounce. lapdata's MINIMUM_LAP_TIME drops the second one, but we
    want to know it happens."""
    last: dict[tuple[int, int], Crossing] = {}
    doubles = []
    for c in crossings:
        key = (c.car, c.lane)
        if key in last and (c.device_ms - last[key].device_ms) / 1000 < within_s:
            doubles.append({'car': c.car, 'lane': c.lane, 'gap_ms': c.device_ms - last[key].device_ms})
        last[key] = c
    return doubles


def both_sensors_at_once(crossings: list[Crossing]) -> int:
    """Packets where one car changed BOTH StartFinish fields — would publish two
    crossings for one real one."""
    per_packet = Counter((c.arrival, c.car) for c in crossings)
    return sum(1 for n in per_packet.values() if n > 1)


def classify_halt_clock(device_elapsed_s: float, wall_elapsed_s: float, halt_s: float,
                        tolerance_s: float = 1.0) -> str:
    """What POWER_ON_TIMER_HALT did to the powerbase clock, from one crossing either side
    of a halt lasting halt_s:
      'paused'       device time skipped the halt (ble_to_timestamps' assumption)
      'kept_ticking' device time ran on through the halt
      'reset'        device time went backwards (zeroed)
      'unclear'      neither within tolerance — rerun, or lengthen the halt"""
    if device_elapsed_s < 0:
        return 'reset'
    paused_error = abs(device_elapsed_s - (wall_elapsed_s - halt_s))
    ticking_error = abs(device_elapsed_s - wall_elapsed_s)
    if paused_error <= tolerance_s and paused_error < ticking_error:
        return 'paused'
    if ticking_error <= tolerance_s and ticking_error < paused_error:
        return 'kept_ticking'
    return 'unclear'


def classify_halted_crossing(pushed: Crossing | None, before: Crossing, halt_at: float,
                             tolerance_s: float = 1.0) -> str:
    """A car pushed over the sensor during a halt: was its timestamp the frozen clock
    ('frozen_at_halt'), a live one ('ticking'), not reported at all ('not_reported'), or
    neither ('unclear')?"""
    if pushed is None:
        return 'not_reported'
    device_s = pushed.device_ms / 1000
    frozen_s = before.device_ms / 1000 + (halt_at - before.arrival)
    ticking_s = before.device_ms / 1000 + (pushed.arrival - before.arrival)
    frozen_error, ticking_error = abs(device_s - frozen_s), abs(device_s - ticking_s)
    if frozen_error <= tolerance_s and frozen_error < ticking_error:
        return 'frozen_at_halt'
    if ticking_error <= tolerance_s and ticking_error < frozen_error:
        return 'ticking'
    return 'unclear'


def estimate_drift_ppm(crossings: list[Crossing], window_s: float = 60.0) -> float | None:
    """Powerbase clock rate against ours, in parts per million. The minimum offset in a
    window is its best estimate of the true offset, so compare the first and last
    windows. Positive means the powerbase clock runs slow, which the running-minimum
    anchor can't follow: stamps then drift early by ppm × seconds since anchoring."""
    if len(crossings) < 2:
        return None
    start, end = crossings[0].arrival, crossings[-1].arrival
    if end - start < 3 * window_s:
        return None

    def best_offset(window):
        return min(c.arrival - c.device_ms / 1000 for c in window)

    first = best_offset([c for c in crossings if c.arrival - start <= window_s])
    last = best_offset([c for c in crossings if end - c.arrival <= window_s])
    return round((last - first) / (end - start - window_s) * 1e6, 1)


def values_retained(before: dict, after: dict) -> bool | None:
    """Did every car seen both sides of a reconnect report the same timestamps?"""
    common = before.keys() & after.keys()
    if not common:
        return None
    return all(before[car] == after[car] for car in common)


# ------------------------------------------------------------------- operator + device

async def ask(prompt: str) -> str:
    # In a thread, so Slot notifications keep being recorded while the operator acts.
    return (await asyncio.to_thread(input, f"\n>>> {prompt}\n    ")).strip()


async def ask_yes_no(prompt: str) -> bool | None:
    """True / False, or None if the operator skips."""
    while True:
        answer = (await ask(f"{prompt} [y / n / s = skip]")).lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        if answer in ('s', 'skip'):
            return None


class Session:
    def __init__(self, device, args):
        self.device = device
        self.args = args
        self.client: BleakClient | None = None
        self.connected_at = 0.0
        self.samples: list[SlotSample] = []
        self.packet_lengths: Counter = Counter()
        self.report = {
            'started': datetime.now(timezone.utc).isoformat(),
            'device': {'address': device.address, 'name': repr(device.name),
                       'name_matches_ble_filter': ble._name_matches(device, None)},
            'checks': {},
        }

    def on_slot(self, _sender, data: bytearray):
        self.packet_lengths[len(data)] += 1
        decoded = ble.decode_slot(data)
        if decoded:
            self.samples.append(SlotSample(time.time(), *decoded))

    async def connect(self, attempts: int = 6):
        for attempt in range(1, attempts + 1):
            try:
                self.client = BleakClient(self.device.address)
                await self.client.connect()
                await self.client.start_notify(ble.SLOT_CHARACTERISTIC_UUID, self.on_slot)
                self.connected_at = time.time()
                print("    Connected, subscribed to Slot notifications.")
                return
            except Exception as e:
                print(f"    Connect attempt {attempt}/{attempts} failed: {e!r}")
                await asyncio.sleep(5)
        raise ConnectionError(f"Could not connect to {self.device.address}")

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            print("    Disconnected.")

    async def write(self, command: int) -> dict:
        at = time.time()
        try:
            await self.client.write_gatt_char(ble.COMMAND_CHARACTERISTIC_UUID, ble.command_payload(command))
        except Exception as e:
            print(f"    Command {command} write FAILED: {e!r}")
            return {'command': command, 'ok': False, 'at': at, 'error': repr(e)}
        print(f"    Command {command} written.")
        return {'command': command, 'ok': True, 'at': at}

    def last_values(self) -> dict:
        values = {}
        for s in self.samples:
            values[s.car] = [s.t1, s.t2]
        return values

    def first_values(self, after: float) -> dict:
        values = {}
        for s in self.samples:
            if s.arrival > after and s.car not in values:
                values[s.car] = [s.t1, s.t2]
        return values

    async def wait_for_crossing(self, instruction: str, timeout_s: float = 90) -> Crossing | None:
        since = time.time()
        print(f"\n>>> {instruction} (waiting up to {timeout_s:.0f}s)")
        while time.time() - since < timeout_s:
            found = find_crossings(self.samples, after=since)
            if found:
                c = found[0]
                print(f"    Crossing: car {c.car}, StartFinish{c.lane}, device {c.device_ms}ms")
                return c
            await asyncio.sleep(0.1)
        print("    No crossing seen.")
        return None

    def save(self):
        with open(self.args.report, 'w') as f:
            json.dump(self.report, f, indent=2, default=str)


# -------------------------------------------------------------------------- checks

CHECKS = []


def check(check_id: str, title: str):
    def register(fn):
        CHECKS.append((check_id, title, fn))
        return fn
    return register


@check('HW-01', 'GATT layout and advertised name')
async def check_gatt(s: Session) -> dict:
    properties = {
        ch.uuid.lower(): sorted(ch.properties)
        for service in s.client.services
        for ch in service.characteristics
    }
    found = {
        'slot': properties.get(ble.SLOT_CHARACTERISTIC_UUID),
        'command': properties.get(ble.COMMAND_CHARACTERISTIC_UUID),
        'throttle': properties.get(THROTTLE_CHARACTERISTIC_UUID),
        'track': properties.get(TRACK_CHARACTERISTIC_UUID),
    }
    slot_ok = 'notify' in (found['slot'] or [])
    command_ok = bool({'write', 'write-without-response'} & set(found['command'] or []))
    return {
        'verdict': verdict(slot_ok and command_ok and s.report['device']['name_matches_ble_filter']),
        'characteristic_properties': found,
    }


@check('HW-02', 'Slot notifications at rest: size, cadence, timestamps retained on connect')
async def check_slot_idle(s: Session) -> dict:
    since = time.time()
    print("\n>>> Leave every car stationary. Listening for 10s...")
    await asyncio.sleep(10)
    window = [x for x in s.samples if x.arrival > since]
    changes = find_crossings(s.samples, after=since)
    return {
        'verdict': verdict(bool(window) and set(s.packet_lengths) == {18} and not changes),
        'packet_lengths': dict(s.packet_lengths),
        'cars_reporting': sorted({x.car for x in window}),
        'cadence': notification_intervals(window),
        'timestamp_changes_while_stationary': len(changes),
        'timestamps_on_connect': s.first_values(after=float('-inf')),
    }


@check('HW-03', 'Command write accepted; POWER_ON_RACING at full multiplier gives full throttle')
async def check_full_power(s: Session) -> dict:
    write = await s.write(ble.POWER_ON_RACING)
    drives = await ask_yes_no("Pull each controller's trigger in turn. Does every car drive at normal full speed?")
    return {'verdict': verdict(write['ok'] and drives), 'write': write, 'full_speed': drives}


@check('HW-04', 'Crossings: car ID byte, which StartFinish field each lane sets, bounce, jitter')
async def check_crossings(s: Session) -> dict:
    await s.write(ble.POWER_ON_RACING)
    car_answer = await ask("Which digital car ID (1-6) will you drive for this check?")
    expected_car = int(car_answer) if car_answer.isdigit() else None
    per_lane, everything, wrong = {}, [], []
    for lane in (1, 2):
        since = time.time()
        await ask(f"Drive car {car_answer} in LANE {lane} (no lane changes) across start/finish "
                  f"5 times, with no other car moving. Press Enter when done.")
        found = find_crossings(s.samples, after=since)
        everything += found
        wrong += [asdict(c) for c in found
                  if c.lane != lane or (expected_car and c.car != expected_car)]
        per_lane[lane] = {
            'crossings_seen': len(found),
            'car_ids_seen': sorted({c.car for c in found}),
            'fields_changed': dict(Counter(c.lane for c in found)),
            'laps': lap_deltas(found),
        }
    return {
        'verdict': verdict(bool(everything) and not wrong and both_sensors_at_once(everything) == 0),
        'per_lane': per_lane,
        'unexpected_crossings': wrong,
        'packets_changing_both_fields': both_sensors_at_once(everything),
        'double_triggers': double_triggers(everything),
        'lateness': reporting_lateness(everything),
    }


@check('HW-05', 'No keepalive: power stays on for 2 minutes with no command writes')
async def check_keepalive(s: Session) -> dict:
    write = await s.write(ble.POWER_ON_RACING)
    print("\n>>> No commands will be written for 120s. Drive a car now and then.")
    for remaining in range(120, 0, -10):
        print(f"    {remaining}s...")
        await asyncio.sleep(10)
    still_notifying = any(x.arrival > time.time() - 5 for x in s.samples)
    powered = await ask_yes_no("Does the car still have power?")
    return {'verdict': verdict(write['ok'] and still_notifying and powered),
            'slot_notifications_still_flowing': still_notifying, 'still_powered': powered}


HALT_CLOCK_IMPACT = {
    'paused': "Matches ble_to_timestamps: _note_command_applied() re-anchors after a halt. No change.",
    'kept_ticking': "The re-anchor after a halt is unnecessary (harmless, costs a few crossings "
                    "of precision) and can be dropped.",
    'reset': "The backwards-timestamp reset path already re-anchors; revisit seeding after a halt.",
    'unclear': "Rerun HW-06. If still unclear, raise HALT_TEST_SECONDS.",
}


@check('HW-06', 'POWER_ON_TIMER_HALT: cuts power, and what it does to the timestamp clock')
async def check_halt(s: Session) -> dict:
    await s.write(ble.POWER_ON_RACING)
    before = await s.wait_for_crossing("Drive one car across start/finish once.")
    if before is None:
        return {'verdict': 'skipped', 'reason': 'no crossing before the halt'}

    halt = await s.write(ble.POWER_ON_TIMER_HALT)
    power_cut = await ask_yes_no("Did every car lose power immediately (triggers do nothing)?")
    await asyncio.sleep(max(0.0, 5 - (time.time() - halt['at'])))
    pushed = await s.wait_for_crossing("While halted: PUSH a car by hand across start/finish.", timeout_s=30)
    remaining = HALT_TEST_SECONDS - (time.time() - halt['at'])
    if remaining > 0:
        print(f"    Holding the halt another {remaining:.0f}s...")
        await asyncio.sleep(remaining)

    resume = await s.write(ble.POWER_ON_RACING)
    power_back = await ask_yes_no("Power should be back. Do the cars drive again?")
    after = await s.wait_for_crossing("Drive one car across start/finish once.")
    result = {
        'writes': {'halt': halt, 'resume': resume},
        'power_cut_immediately': power_cut,
        'power_restored_on_resume': power_back,
        'halt_seconds': round(resume['at'] - halt['at'], 2),
        'crossing_before': asdict(before),
        'crossing_during_halt': asdict(pushed) if pushed else None,
        'crossing_during_halt_timestamp': classify_halted_crossing(pushed, before, halt['at']),
    }
    if after is None:
        return {'verdict': 'skipped', 'reason': 'no crossing after resume', **result}

    clock = classify_halt_clock((after.device_ms - before.device_ms) / 1000,
                                after.arrival - before.arrival, resume['at'] - halt['at'])
    result.update(crossing_after=asdict(after), clock=clock, code_impact=HALT_CLOCK_IMPACT[clock])
    ok = power_cut and power_back
    result['verdict'] = 'fail' if ok is False else ('pass' if ok and clock == 'paused' else 'review')
    return result


@check('HW-07', 'Track power when BLE disconnects (halted and racing), timestamps kept on reconnect')
async def check_disconnect(s: Session) -> dict:
    result = {}
    for command, label in ((ble.POWER_ON_TIMER_HALT, 'halted'), (ble.POWER_ON_RACING, 'racing')):
        await s.write(command)
        before = s.last_values()
        await s.disconnect()
        powered_disconnected = await ask_yes_no(
            f"BLE is DISCONNECTED while {label}. Wait 10s, then try a trigger: does the track have power?")
        await s.connect()
        await asyncio.sleep(3)
        powered_reconnected = await ask_yes_no("Reconnected, no command sent yet. Does the track have power?")
        result[label] = {
            'track_power_while_disconnected': powered_disconnected,
            'track_power_after_reconnect_before_any_write': powered_reconnected,
            'timestamps_retained': values_retained(before, s.first_values(after=s.connected_at)),
        }
    await s.write(ble.POWER_ON_RACING)

    notes = []
    if result['halted']['track_power_while_disconnected']:
        notes.append("SAFETY: a BLE drop during a yellow-flag power cut restores track power, and no "
                     "software can prevent it. Marshals must not rely on the cut while BLE is unstable.")
    if result['racing']['track_power_while_disconnected'] is False:
        notes.append("A BLE drop mid-race stops every car until the ble container reconnects.")
    if result['halted']['timestamps_retained'] is False or result['racing']['timestamps_retained'] is False:
        notes.append("Timestamps changed across a reconnect: revisit the seeding logic.")
    expected = (result['halted']['track_power_while_disconnected'] is False
                and result['racing']['track_power_while_disconnected'] is True)
    return {'verdict': 'pass' if expected and not notes else 'review', **result, 'code_impact': notes}


@check('HW-08', 'Powerbase power-cycle: timers after, track power before any app command')
async def check_power_cycle(s: Session) -> dict:
    await s.disconnect()
    await ask("Switch the powerbase OFF, wait 5s, switch it back ON. Press Enter once it is on.")
    await s.connect()
    await asyncio.sleep(3)
    powered = await ask_yes_no("Reconnected, no command sent. Does the track have power?")
    values = s.first_values(after=s.connected_at)
    await s.write(ble.POWER_ON_RACING)
    return {'verdict': 'info', 'timestamps_after_power_cycle': values,
            'track_power_before_any_write': powered}


@check('HW-09', 'NO_POWER_TIMER_STOPPED (command 0) zeroes the Slot timestamps')
async def check_timer_reset(s: Session) -> dict:
    await s.write(ble.POWER_ON_RACING)
    before = await s.wait_for_crossing("Drive a car across start/finish once, so it has a non-zero timestamp.")
    if before is None:
        return {'verdict': 'skipped', 'reason': 'no crossing before the reset'}
    reset = await s.write(ble.NO_POWER_TIMER_STOPPED)
    await asyncio.sleep(3)
    zeroed = s.first_values(after=reset['at'] + 1).get(before.car) == [0, 0]
    await s.write(ble.POWER_ON_RACING)
    after = await s.wait_for_crossing("Drive a car across start/finish once more.")
    went_backwards = after is not None and after.device_ms < before.device_ms
    return {'verdict': verdict(reset['ok'] and zeroed and went_backwards),
            'timestamps_zeroed': zeroed, 'next_crossing_counts_from_zero': went_backwards,
            'crossing_before': asdict(before), 'crossing_after': asdict(after) if after else None}


@check('HW-10', 'Reporting delay and powerbase clock drift over a long run')
async def check_drift(s: Session) -> dict:
    await s.write(ble.POWER_ON_RACING)
    minutes = s.args.drift_minutes
    since = time.time()
    end = since + minutes * 60
    print(f"\n>>> Drive a car in steady laps for {minutes} minutes. No halts in this check.")
    while time.time() < end:
        await asyncio.sleep(min(30, max(0.0, end - time.time())))
        print(f"    {max(0.0, end - time.time()) / 60:.1f} min left, "
              f"{len(find_crossings(s.samples, after=since))} crossings")
    found = find_crossings(s.samples, after=since)
    return {'verdict': 'info', 'crossings': len(found), 'lateness': reporting_lateness(found),
            'drift_ppm': estimate_drift_ppm(found), 'double_triggers': double_triggers(found)}


# ---------------------------------------------------------------------------- main

async def find_device(address: str | None):
    if address:
        device = await BleakScanner.find_device_by_address(address, timeout=20)
    else:
        device = await BleakScanner.find_device_by_filter(ble._name_matches, timeout=20)
    if device is None:
        raise SystemExit("No powerbase found. Is it on, in range, and is the ble container stopped?")
    print(f"Found {device.name!r} at {device.address}")
    return device


async def main(args):
    selected = [c for c in CHECKS if not args.only or c[0] in args.only]
    s = Session(await find_device(args.address), args)
    await s.connect()
    try:
        for check_id, title, fn in selected:
            print(f"\n=== {check_id}: {title}")
            try:
                result = await fn(s)
            except Exception as e:
                print(f"    {check_id} errored: {e!r}")
                result = {'verdict': 'error', 'error': repr(e)}
                if not (s.client and s.client.is_connected):
                    await s.connect()
            s.report['checks'][check_id] = {'title': title, **result}
            s.save()
            print(f"    -> {result['verdict'].upper()}")
    finally:
        s.save()
        await s.disconnect()

    print(f"\nReport written to {args.report}\n")
    for check_id, entry in s.report['checks'].items():
        print(f"  {check_id}  {entry['verdict'].upper():8} {entry['title']}")
    print("\nRestart the Layer 1 afterwards: docker start ble")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--address', default=os.getenv('BLE_ADDRESS') or None,
                        help="powerbase MAC; defaults to BLE_ADDRESS, else scan by name")
    parser.add_argument('--only', type=lambda v: {x.strip().upper() for x in v.split(',')},
                        help="comma-separated check IDs, e.g. HW-06,HW-07")
    parser.add_argument('--report', default='hw-report.json')
    parser.add_argument('--drift-minutes', type=float, default=5)
    asyncio.run(main(parser.parse_args()))
