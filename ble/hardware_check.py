"""Hardware validation for the BLE Layer 1.

Answers the questions in HARDWARE_VALIDATION.md against a real Scalextric ARC Pro
powerbase: everything ble_to_timestamps.py assumes about the hardware that unit tests
can't prove. Each check has an ID (HW-01...), prompts the operator where a human has to
drive a car or look at the track, and writes what it observed to a JSON report. The
analysis is pure functions, covered by test_hardware_check.py. Packet decoding and the
Command payload are imported from ble_to_timestamps, so it is the production code's
view of the hardware that gets checked.

⚠️ Stop the ble container first (the powerbase takes one BLE connection at a time), and
never run this during a race: it cuts track power, and HW-09, HW-11 and HW-12 zero the lap
timers.

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

TRACK_CHARACTERISTIC_UUID = "00003b0c-0000-1000-8000-00805f9b34fb"

# Long enough that "clock paused through the halt" and "clock kept ticking" differ by far
# more than a round-robin reporting delay.
HALT_TEST_SECONDS = 15
# Same reasoning for HW-11: "zeroed at command 1 and ticked" and "held at zero until
# command 3" must differ by more than a crossing's reporting delay.
READY_HOLD_SECONDS = 10
# HW-12 reads throttleTimestamp directly rather than waiting for crossings, and
# notifications come many times a second, so shorter windows and tolerances will do.
THROTTLE_WINDOW_SECONDS = 10
THROTTLE_TOLERANCE_S = 0.5
# Samples arriving within this long of a write's acknowledgement may have been generated
# before the powerbase acted on it.
SETTLE_S = 0.5


@dataclass(frozen=True)
class SlotSample:
    arrival: float      # unix seconds on this machine
    car: int
    t1: int             # StartFinish1, powerbase ticks (ble.DEVICE_TICK_S)
    t2: int             # StartFinish2, powerbase ticks


@dataclass(frozen=True)
class Crossing:
    arrival: float
    car: int
    lane: int           # which StartFinish field changed
    device_ticks: int   # raw; convert with ble.device_seconds()


@dataclass(frozen=True)
class ThrottleSample:
    arrival: float
    timestamp_ticks: int   # throttleTimestamp, powerbase ticks
    throttles: tuple    # six raw per-car throttle bytes


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


def _lateness(offsets: list[float], label: str) -> dict:
    anchor = min(offsets)
    late_ms = sorted((o - anchor) * 1000 for o in offsets)
    return {
        label: len(late_ms),
        'median_ms': round(statistics.median(late_ms)),
        'p95_ms': round(late_ms[min(len(late_ms) - 1, int(len(late_ms) * 0.95))]),
        'max_ms': round(late_ms[-1]),
    }


def reporting_lateness(crossings: list[Crossing]) -> dict | None:
    """How late each crossing was reported, relative to the least-delayed one: the same
    running-minimum anchor ble_to_timestamps uses. Only meaningful over a stretch with
    no halt or timer reset in it."""
    if len(crossings) < 2:
        return None
    return _lateness([c.arrival - ble.device_seconds(c.device_ticks) for c in crossings], 'crossings')


def lap_deltas(crossings: list[Crossing]) -> list[dict]:
    """Consecutive crossings by the same car: the lap on the powerbase clock against the
    lap on ours. The difference is the reporting jitter device timestamps keep out."""
    deltas = []
    for a, b in zip(crossings, crossings[1:]):
        if a.car == b.car:
            device_s = ble.device_seconds(b.device_ticks - a.device_ticks)
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
        gap_s = ble.device_seconds(c.device_ticks - last[key].device_ticks) if key in last else None
        if gap_s is not None and gap_s < within_s:
            doubles.append({'car': c.car, 'lane': c.lane, 'gap_ms': round(gap_s * 1000)})
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
    device_s = ble.device_seconds(pushed.device_ticks)
    frozen_s = ble.device_seconds(before.device_ticks) + (halt_at - before.arrival)
    ticking_s = ble.device_seconds(before.device_ticks) + (pushed.arrival - before.arrival)
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
        return min(c.arrival - ble.device_seconds(c.device_ticks) for c in window)

    first = best_offset([c for c in crossings if c.arrival - start <= window_s])
    last = best_offset([c for c in crossings if end - c.arrival <= window_s])
    return round((last - first) / (end - start - window_s) * 1e6, 1)


def values_retained(before: dict, after: dict) -> bool | None:
    """Did every car seen both sides of a reconnect report the same timestamps?"""
    common = before.keys() & after.keys()
    if not common:
        return None
    return all(before[car] == after[car] for car in common)


def compare_poll_to_notify(polled: list[SlotSample], notified: list[SlotSample]) -> dict:
    """HW-14: does reading the Slot characteristic see crossings sooner than waiting for
    its notifications? Both streams are edge-detected the same way, and each crossing is
    identified by (car, lane, device ticks), so the same crossing seen by both can be
    compared. `earlier_ms` is how much sooner polling saw it (negative: later)."""
    def first_seen(samples):
        seen = {}
        for c in find_crossings(samples):
            seen.setdefault((c.car, c.lane, c.device_ticks), c.arrival)
        return seen

    by_poll, by_notify = first_seen(polled), first_seen(notified)
    common = by_poll.keys() & by_notify.keys()
    earlier_ms = sorted(round((by_notify[k] - by_poll[k]) * 1000) for k in common)
    ids = [s.car for s in polled]
    wall_s = polled[-1].arrival - polled[0].arrival if len(polled) > 1 else 0
    return {
        'reads': len(polled),
        'reads_per_s': round(len(polled) / wall_s, 1) if wall_s > 0 else None,
        # 1.0: every read returns the next car. ~0.1 or less: reads repeat the last notification.
        'car_id_change_fraction': (round(sum(a != b for a, b in zip(ids, ids[1:])) / (len(ids) - 1), 3)
                                   if len(ids) > 1 else None),
        'cars_seen_by_polling': sorted(set(ids)),
        'per_car_refresh_by_polling': notification_intervals(polled),
        'crossings': {'seen_by_both': len(common), 'only_polling': len(by_poll.keys() - common),
                      'only_notify': len(by_notify.keys() - common)},
        'polling_earlier_ms': ({'median': earlier_ms[len(earlier_ms) // 2], 'min': earlier_ms[0],
                                'max': earlier_ms[-1]} if earlier_ms else None),
    }


def samples_between(samples: list, start: float, end: float) -> list:
    return [s for s in samples if start <= s.arrival <= end]


def last_before(samples: list, t: float):
    found = [s for s in samples if s.arrival < t]
    return found[-1] if found else None


def first_after(samples: list, t: float):
    return next((s for s in samples if s.arrival > t), None)


def classify_ready_clock(device_s: float, since_ready_s: float, since_go_s: float,
                         tolerance_s: float = 1.0) -> str:
    """Where the powerbase clock restarted, from a crossing's stamp after command 1 (ready)
    was held for a while and then command 3 (go) sent:
      'ticked_from_ready'  zeroed at command 1 and ticking from there
      'started_at_go'      held at zero until command 3
      'not_reset'          larger than the time since command 1, so it was never zeroed
      'unclear'            neither within tolerance"""
    if device_s > since_ready_s + tolerance_s:
        return 'not_reset'
    ready_error, go_error = abs(device_s - since_ready_s), abs(device_s - since_go_s)
    if ready_error <= tolerance_s and ready_error < go_error:
        return 'ticked_from_ready'
    if go_error <= tolerance_s and go_error < ready_error:
        return 'started_at_go'
    return 'unclear'


def classify_resend(device_elapsed_s: float, wall_elapsed_s: float, tolerance_s: float = 1.0) -> str:
    """What re-sending POWER_ON_RACING while already racing did to the clock, from one
    crossing either side: 'unaffected', 'reset' (went backwards), or 'unclear'."""
    if device_elapsed_s < 0:
        return 'reset'
    return 'unaffected' if abs(device_elapsed_s - wall_elapsed_s) <= tolerance_s else 'unclear'


def throttle_stream(samples: list[ThrottleSample]) -> dict | None:
    """Cadence, liveness and lateness of throttleTimestamp over a stretch with no halt or
    reset in it. A live clock reading advances on (nearly) every notification at the
    rate of our clock. A timestamp that only moves when a throttle changes would show a
    low advancing_fraction and a rate well under 1 while the triggers are released."""
    if len(samples) < 2:
        return None
    pairs = list(zip(samples, samples[1:]))
    wall_s = samples[-1].arrival - samples[0].arrival
    device_s = ble.device_seconds(samples[-1].timestamp_ticks - samples[0].timestamp_ticks)
    gaps = [b.arrival - a.arrival for a, b in pairs]
    return {
        'median_gap_ms': round(statistics.median(gaps) * 1000),
        'max_gap_ms': round(max(gaps) * 1000),
        'advancing_fraction': round(sum(b.timestamp_ticks > a.timestamp_ticks for a, b in pairs) / len(pairs), 3),
        'device_to_wall_rate': round(device_s / wall_s, 4) if wall_s > 0 else None,
        'lateness': _lateness([s.arrival - ble.device_seconds(s.timestamp_ticks) for s in samples], 'notifications'),
    }


def max_throttle_per_car(samples: list[ThrottleSample]) -> list[int] | None:
    """Highest throttle reading (0-63, brake and lane-change bits masked off) for each of
    cars 1-6. With the triggers released this is each controller's noise floor, which a
    jump-start threshold has to sit above."""
    if not samples:
        return None
    return [max(s.throttles[i] & 0x3F for s in samples) for i in range(6)]


def is_live(stream: dict | None, rate_tolerance: float = 0.05, min_advancing: float = 0.9) -> bool | None:
    if not stream or stream['device_to_wall_rate'] is None:
        return None
    return (abs(stream['device_to_wall_rate'] - 1) <= rate_tolerance
            and stream['advancing_fraction'] >= min_advancing)


def compare_clock_offsets(throttle: list[ThrottleSample], crossings: list[Crossing],
                          tolerance_s: float = THROTTLE_TOLERANCE_S) -> dict | None:
    """Anchor our clock to throttleTimestamp and, separately, to the Slot crossing stamps
    over the same stretch. If both are readings of one powerbase clock, both anchors are
    estimates of the same offset and agree to within a reporting delay. Two timers that
    merely started together (say, one per chip at power-on) could also agree, which is why
    HW-12 also checks that they halt and zero together."""
    if not throttle or not crossings:
        return None
    throttle_offset = min(s.arrival - ble.device_seconds(s.timestamp_ticks) for s in throttle)
    slot_offset = min(c.arrival - ble.device_seconds(c.device_ticks) for c in crossings)
    difference = slot_offset - throttle_offset
    return {
        'throttle_offset_s': round(throttle_offset, 3),
        'slot_offset_s': round(slot_offset, 3),
        'slot_minus_throttle_ms': round(difference * 1000),
        'agree': abs(difference) <= tolerance_s,
    }


def classify_clock_window(samples: list[ThrottleSample], start: float, end: float,
                          tolerance_s: float = THROTTLE_TOLERANCE_S) -> dict:
    """What throttleTimestamp did between two instants, e.g. through a halt: 'ticking',
    'halted', 'went_backwards', 'too_short' to tell, 'no_data', or 'unclear'."""
    window = samples_between(samples, start, end)
    if len(window) < 2:
        return {'behaviour': 'no_data'}
    first, last = window[0], window[-1]
    device_s = ble.device_seconds(last.timestamp_ticks - first.timestamp_ticks)
    wall_s = last.arrival - first.arrival
    if device_s < -tolerance_s:
        behaviour = 'went_backwards'
    elif wall_s <= 2 * tolerance_s:
        behaviour = 'too_short'
    elif abs(device_s) <= tolerance_s:
        behaviour = 'halted'
    elif abs(device_s - wall_s) <= tolerance_s:
        behaviour = 'ticking'
    else:
        behaviour = 'unclear'
    return {'behaviour': behaviour, 'first_ticks': first.timestamp_ticks, 'last_ticks': last.timestamp_ticks,
            'device_s': round(device_s, 3), 'wall_s': round(wall_s, 3)}


def clock_zeroed(before: ThrottleSample | None, after: ThrottleSample | None, write_at: float,
                 tolerance_s: float = THROTTLE_TOLERANCE_S) -> bool | None:
    """Did a write zero throttleTimestamp? Yes if the first sample after it reads no more
    than the time since the write was sent, and less than the last sample before it."""
    if after is None:
        return None
    near_zero = ble.device_seconds(after.timestamp_ticks) <= (after.arrival - write_at) + tolerance_s
    dropped = before is None or after.timestamp_ticks < before.timestamp_ticks
    return near_zero and dropped


def bytes_new_in_window(baseline: list[tuple[str, bytes]], window: list[tuple[str, bytes]]) -> dict:
    """Per characteristic, byte positions that were constant through the baseline but took
    other values in the window, e.g. while pressing buttons. Positions that already varied
    in the baseline (sequence counters, live timestamps) are noise and are left out."""
    seen: dict[tuple[str, int], set] = {}
    for name, data in baseline:
        for i, b in enumerate(data):
            seen.setdefault((name, i), set()).add(b)
    found: dict[str, dict[int, list[int]]] = {}
    for name, data in window:
        for i, b in enumerate(data):
            base = seen.get((name, i))
            if base is not None and len(base) == 1 and b not in base:
                found.setdefault(name, {}).setdefault(i, set()).add(b)
    return {name: {i: sorted(v) for i, v in sorted(positions.items())} for name, positions in found.items()}


def conclude_same_clock(evidence: dict) -> str:
    """'different_clock' if any comparison with the Slot clock disagrees, 'same_clock' if
    the offsets agree and nothing disagrees, else 'unclear'. None means not measured."""
    if any(v is False for v in evidence.values()):
        return 'different_clock'
    return 'same_clock' if evidence.get('offsets_agree') else 'unclear'


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
        self.throttle: list[ThrottleSample] = []
        self.throttle_error: str | None = None
        # Every notification's raw bytes, for HW-13's hunt for undocumented fields.
        self.raw: list[tuple[float, str, bytes]] = []
        self.report = {
            'started': datetime.now(timezone.utc).isoformat(),
            'device': {'address': device.address, 'name': repr(device.name),
                       'name_matches_ble_filter': ble._name_matches(device, None)},
            'checks': {},
        }

    def on_slot(self, _sender, data: bytearray):
        self.raw.append((time.time(), 'slot', bytes(data)))
        self.packet_lengths[len(data)] += 1
        decoded = ble.decode_slot(data)
        if decoded:
            self.samples.append(SlotSample(time.time(), *decoded))

    def on_throttle(self, _sender, data: bytearray):
        self.raw.append((time.time(), 'throttle', bytes(data)))
        decoded = ble.decode_throttle(data)
        if decoded:
            self.throttle.append(ThrottleSample(time.time(), *decoded))

    def on_track(self, _sender, data: bytearray):
        self.raw.append((time.time(), 'track', bytes(data)))

    async def connect(self, attempts: int = 6):
        for attempt in range(1, attempts + 1):
            try:
                self.client = BleakClient(self.device.address)
                await self.client.connect()
                await self.client.start_notify(ble.SLOT_CHARACTERISTIC_UUID, self.on_slot)
                self.connected_at = time.time()
                print("    Connected, subscribed to Slot notifications.")
                # Only HW-12 needs it, so a base without it mustn't fail the whole run.
                try:
                    await self.client.start_notify(ble.THROTTLE_CHARACTERISTIC_UUID, self.on_throttle)
                    self.throttle_error = None
                except Exception as e:
                    self.throttle_error = repr(e)
                    print(f"    No Throttle notifications ({e!r}). HW-12 will fail.")
                try:
                    await self.client.start_notify(TRACK_CHARACTERISTIC_UUID, self.on_track)
                except Exception as e:
                    print(f"    No Track notifications ({e!r}).")
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
        """`at` is when the write was sent and `acked_at` when bleak returned, so the
        powerbase acted on it somewhere in between (with-response writes, which HW-01's
        characteristic properties confirm)."""
        at = time.time()
        try:
            await self.client.write_gatt_char(ble.COMMAND_CHARACTERISTIC_UUID, ble.command_payload(command))
        except Exception as e:
            acked_at = time.time()
            print(f"    Command {command} write FAILED: {e!r}")
            return {'command': command, 'ok': False, 'at': at, 'acked_at': acked_at, 'error': repr(e)}
        acked_at = time.time()
        print(f"    Command {command} written ({(acked_at - at) * 1000:.0f}ms).")
        return {'command': command, 'ok': True, 'at': at, 'acked_at': acked_at,
                'latency_ms': round((acked_at - at) * 1000)}

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
                print(f"    Crossing: car {c.car}, StartFinish{c.lane}, device {ble.device_seconds(c.device_ticks):.2f}s")
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
        'throttle': properties.get(ble.THROTTLE_CHARACTERISTIC_UUID),
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
    # The first run (2026-09-18) got no Slot packets at all until a Command was written,
    # here and after HW-08's power cycle. ble writes one on connect, so it works, but
    # measure both: before, and after a write.
    before_write = [x for x in s.samples if x.arrival > since]
    written = None
    if not before_write:
        print("    No Slot packets before any Command write. Writing POWER_ON_RACING, listening 10s more...")
        written = await s.write(ble.POWER_ON_RACING)
        since = time.time()
        await asyncio.sleep(10)
    window = [x for x in s.samples if x.arrival > since]
    changes = find_crossings(s.samples, after=since)
    return {
        # The doc says 18 bytes; a real ARC Pro sends 20 (2026-09-18). decode_slot() reads 10.
        'verdict': verdict(bool(window) and min(s.packet_lengths, default=0) >= 18 and not changes),
        'notifies_before_first_command': bool(before_write),
        'write': written,
        'packet_lengths': dict(s.packet_lengths),
        'cars_reporting': sorted({x.car for x in window}),
        # One car's gap is a full round-robin rotation: the worst-case reporting delay.
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

    clock = classify_halt_clock(ble.device_seconds(after.device_ticks - before.device_ticks),
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
            f"BLE is DISCONNECTED while {label}. Wait 10s, then try a trigger briefly, WITHOUT crossing "
            f"start/finish (a crossing changes the timestamps this also checks). Does the track have power?")
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
    went_backwards = after is not None and after.device_ticks < before.device_ticks
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


READY_CLOCK_IMPACT = {
    'ticked_from_ready': "Command 1 zeroes the clock and it ticks from there. Plan B (1 then 3 at arm) "
                         "puts the clock's zero at the command 1 write, within its latency.",
    'started_at_go': "Command 1 holds the clock at zero until command 3. Plan B (1 then 3 at arm) puts "
                     "the clock's zero at the command 3 write, within its latency.",
    'not_reset': "Command 1 does not zero the Slot timers: plan B is unavailable, and the comments "
                 "saying commands 0/1 zero them are wrong.",
    'unclear': "Rerun HW-11. If still unclear, raise READY_HOLD_SECONDS.",
}


@check('HW-11', 'Commands 1 then 3 (plan B, sent at arm): where the clock restarts, write latency')
async def check_ready_then_go(s: Session) -> dict:
    await s.write(ble.POWER_ON_RACING)
    before = await s.wait_for_crossing("Drive one car across start/finish once, then stop it.")
    if before is None:
        return {'verdict': 'skipped', 'reason': 'no crossing before command 1'}

    # Held apart, so where the clock restarted is unambiguous.
    ready = await s.write(ble.NO_POWER_TIMER_TICKING)
    held = await ask_yes_no("Command 1 (ready) sent. Pull every trigger: do all cars stay still?")
    remaining = READY_HOLD_SECONDS - (time.time() - ready['at'])
    if remaining > 0:
        print(f"    Holding command 1 another {remaining:.0f}s...")
        await asyncio.sleep(remaining)
    zeroed = s.first_values(after=ready['acked_at'] + SETTLE_S).get(before.car) == [0, 0]
    go = await s.write(ble.POWER_ON_RACING)
    after = await s.wait_for_crossing("Drive one car across start/finish once.")
    result = {
        'writes': {'ready': ready, 'go': go},
        'cars_held_by_command_1': held,
        'slot_timestamps_zeroed': zeroed,
        'throttle_during_ready': classify_clock_window(s.throttle, ready['acked_at'] + SETTLE_S, go['at']),
        'crossing_before': asdict(before),
    }
    notes = []
    if after is None:
        result['clock'] = None
    else:
        clock = classify_ready_clock(ble.device_seconds(after.device_ticks), after.arrival - ready['acked_at'],
                                     after.arrival - go['acked_at'])
        result.update(crossing_after=asdict(after), clock=clock)
        notes.append(READY_CLOCK_IMPACT[clock])
    if held is False:
        notes.append("Command 1 does not hold the cars: plan B's reset at arm lets a car creep, and a "
                     "jump-start hold can't use command 1.")

    # Plan B as it would really run: back-to-back, cars stationary on the grid.
    await ask("Stop every car. Press Enter to send commands 1 and 3 back-to-back.")
    pair_ready = await s.write(ble.NO_POWER_TIMER_TICKING)
    pair_go = await s.write(ble.POWER_ON_RACING)
    pair_crossing = await s.wait_for_crossing("Drive one car across start/finish once.")
    result['plan_b'] = {
        'writes': {'ready': pair_ready, 'go': pair_go},
        'pair_ms': round((pair_go['acked_at'] - pair_ready['at']) * 1000),
        'crossing': asdict(pair_crossing) if pair_crossing else None,
        # Time from sending command 1 to the crossing, minus the clock's reading at it: how
        # long after that send the clock's zero was, plus the crossing's reporting delay.
        'zero_lag_upper_bound_ms': (
            round(((pair_crossing.arrival - pair_ready['at']) - ble.device_seconds(pair_crossing.device_ticks)) * 1000)
            if pair_crossing else None),
    }

    # ble re-sends command 3 on every Running transition and resume: it must not reset.
    resend_before = await s.wait_for_crossing("Drive steady laps. Cross start/finish once.")
    resend = await s.write(ble.POWER_ON_RACING)
    resend_after = await s.wait_for_crossing("Keep driving. Cross start/finish once more.")
    resend_effect = None
    if resend_before and resend_after:
        resend_effect = classify_resend(ble.device_seconds(resend_after.device_ticks - resend_before.device_ticks),
                                        resend_after.arrival - resend_before.arrival)
    result['resend_command_3'] = {'write': resend, 'effect': resend_effect}
    if resend_effect == 'reset':
        notes.append("Re-sending command 3 while racing resets the clock: ble must stop re-sending it, "
                     "or start a new clock epoch each time it does.")

    writes_ok = all(w['ok'] for w in (ready, go, pair_ready, pair_go, resend))
    result['code_impact'] = notes
    result['verdict'] = 'fail' if not writes_ok else ('skipped' if after is None else 'review')
    return result


THROTTLE_CLOCK_IMPACT = {
    'same_clock': "throttleTimestamp reads the Slot clock: ble can publish it as a clock heartbeat "
                  "(plan A), so lap 1 needs no power writes at go or arm.",
    'different_clock': "throttleTimestamp is a different clock: plan A is out. Lap 1 uses plan B "
                       "(commands 1 then 3 at arm, see HW-11), else crossing stamps.",
    'unclear': "Rerun HW-12 in the same run as HW-06 and HW-11, with more crossings.",
}


@check('HW-12', 'throttleTimestamp: a live reading of the same clock as the Slot timestamps?')
async def check_throttle_clock(s: Session) -> dict:
    if s.throttle_error:
        return {'verdict': 'fail', 'reason': f'no Throttle notifications: {s.throttle_error}'}
    await s.write(ble.POWER_ON_RACING)

    # 1. At rest: the case that matters, since the grid is at rest before lights out.
    await ask(f"Release every trigger and leave the cars still. Press Enter to listen for "
              f"{THROTTLE_WINDOW_SECONDS}s.")
    rest_from = time.time()
    await asyncio.sleep(THROTTLE_WINDOW_SECONDS)
    rest_samples = samples_between(s.throttle, rest_from, time.time())
    rest = throttle_stream(rest_samples)

    # 2. Driving: compare against the Slot clock over the same stretch.
    driving_from = time.time()
    await ask("Drive one car across start/finish at least 5 times (with more controllers, pull the "
              "other triggers now and then). Press Enter when done.")
    driving_samples = samples_between(s.throttle, driving_from, time.time())
    crossings = find_crossings(s.samples, after=driving_from)
    offsets = compare_clock_offsets(driving_samples, crossings)

    # 3. Halt: does it freeze with the Slot clock (HW-06)?
    await ask(f"Stop every car. Press Enter to cut power for {THROTTLE_WINDOW_SECONDS}s.")
    halt = await s.write(ble.POWER_ON_TIMER_HALT)
    await asyncio.sleep(THROTTLE_WINDOW_SECONDS)
    resume = await s.write(ble.POWER_ON_RACING)
    await asyncio.sleep(2)
    halt_before = last_before(s.throttle, halt['at'])
    halt_after = first_after(s.throttle, resume['acked_at'] + SETTLE_S)
    halt_clock = None
    if halt_before and halt_after:
        halt_clock = classify_halt_clock(ble.device_seconds(halt_after.timestamp_ticks - halt_before.timestamp_ticks),
                                         halt_after.arrival - halt_before.arrival,
                                         resume['at'] - halt['at'], tolerance_s=THROTTLE_TOLERANCE_S)

    # 4. Command 1: does it zero with the Slot timers (HW-11), and tick or hold?
    ready = await s.write(ble.NO_POWER_TIMER_TICKING)
    await asyncio.sleep(THROTTLE_WINDOW_SECONDS / 2)
    go = await s.write(ble.POWER_ON_RACING)
    await asyncio.sleep(2)
    zeroed = clock_zeroed(last_before(s.throttle, ready['at']),
                          first_after(s.throttle, ready['acked_at'] + SETTLE_S), ready['at'])

    slot_halt = s.report['checks'].get('HW-06', {}).get('clock')
    slot_zeroed = s.report['checks'].get('HW-11', {}).get('slot_timestamps_zeroed')
    evidence = {
        'offsets_agree': offsets['agree'] if offsets else None,
        'halt_matches_slot': (halt_clock == slot_halt
                              if halt_clock and slot_halt in ('paused', 'kept_ticking', 'reset') else None),
        'zeroing_matches_slot': zeroed == slot_zeroed if zeroed is not None and slot_zeroed is not None else None,
    }
    conclusion = conclude_same_clock(evidence)
    live = is_live(rest)
    notes = [THROTTLE_CLOCK_IMPACT[conclusion]]
    if live is False:
        notes.append("throttleTimestamp doesn't advance at rest, so it is no heartbeat on a stationary "
                     "grid, which is exactly when lap 1 needs one.")
    if evidence['halt_matches_slot'] is None or evidence['zeroing_matches_slot'] is None:
        notes.append("Not all evidence was gathered: run HW-06 and HW-11 in the same run.")
    return {
        'verdict': 'pass' if conclusion == 'same_clock' and live else 'review',
        'conclusion': conclusion,
        'live_at_rest': live,
        'evidence': evidence,
        'at_rest': rest,
        'throttle_at_rest_max': max_throttle_per_car(rest_samples),
        'driving': throttle_stream(driving_samples),
        'offsets': offsets,
        'crossings_compared': len(crossings),
        'halt': {'writes': {'halt': halt, 'resume': resume}, 'clock': halt_clock,
                 'during': classify_clock_window(s.throttle, halt['acked_at'] + SETTLE_S, resume['at'])},
        'command_1': {'writes': {'ready': ready, 'go': go}, 'zeroed': zeroed,
                      'during': classify_clock_window(s.throttle, ready['acked_at'] + SETTLE_S, go['at'])},
        'code_impact': notes,
    }


@check('HW-13', 'Powerbase buttons: does pressing them show up anywhere over BLE?')
async def check_base_buttons(s: Session) -> dict:
    """The protocol doc documents controller buttons (brake, lane change, double-tap) but
    nothing for the six buttons on the powerbase itself. Look for any byte, on any
    notifying characteristic, that only changes while they are pressed."""
    await s.write(ble.POWER_ON_RACING)
    await ask("LIFT EVERY CAR OFF THE TRACK (a double click on a base button starts car pairing, "
              "and could re-program a car's ID). Release every trigger and don't touch the base. "
              "Press Enter to record a 10s baseline.")
    base_from = time.time()
    await asyncio.sleep(10)
    base_to = time.time()
    await ask("Now, on each of the 6 powerbase buttons in turn: ONE single click, wait 2s, then "
              "press and hold ~2s. Never double click. Press Enter when done.")
    window_to = time.time()
    baseline = [(n, d) for t, n, d in s.raw if base_from <= t <= base_to]
    window = [(n, d) for t, n, d in s.raw if base_to < t <= window_to]
    found = bytes_new_in_window(baseline, window)
    return {
        'verdict': 'info',
        'visible_over_ble': bool(found),
        'new_bytes_while_pressing': found,
        'packets': {'baseline': dict(Counter(n for n, _ in baseline)),
                    'pressing': dict(Counter(n for n, _ in window))},
    }


POLL_SECONDS = 30


@check('HW-14', 'Polling the Slot characteristic: faster crossings than its notifications?')
async def check_slot_polling(s: Session) -> dict:
    """Notifications come every 300 ms and round-robin 6 car IDs, so a crossing can take
    1.8 s to arrive (HW-02). Slot is also readable (HW-01): read it back-to-back while
    notifications keep flowing, and see whether reads reach a crossing sooner. Also dumps
    the two undocumented bytes (packets are 20 bytes, the doc says 18)."""
    await s.write(ble.POWER_ON_RACING)
    await ask(f"Put car 5 back on the track and drive steady laps, crossing start/finish as often "
              f"as you can. Press Enter once it's lapping; polling runs for {POLL_SECONDS}s.")
    polled: list[SlotSample] = []
    trailing = Counter()
    errors = 0
    start = time.time()
    notified_from = len(s.samples)
    while time.time() - start < POLL_SECONDS:
        try:
            data = await s.client.read_gatt_char(ble.SLOT_CHARACTERISTIC_UUID)
        except Exception:
            errors += 1
            await asyncio.sleep(0.1)
            continue
        trailing[bytes(data[18:]).hex()] += 1
        decoded = ble.decode_slot(bytearray(data))
        if decoded:
            polled.append(SlotSample(time.time(), *decoded))
    notified = s.samples[notified_from:]
    trailing_notified = Counter(data[18:].hex() for t, name, data in s.raw if name == 'slot' and t >= start)
    result = compare_poll_to_notify(polled, notified)
    earlier = result['polling_earlier_ms']
    notes = []
    if earlier and earlier['median'] >= 300:
        notes.append("Polling sees crossings sooner: worth a polling mode in ble_to_timestamps.")
    elif result['crossings']['seen_by_both']:
        notes.append("Polling is no faster than notifications: the 1.8 s rotation stands.")
    return {'verdict': 'info', **result, 'read_errors': errors,
            'trailing_bytes_18_19': {'polled': dict(trailing.most_common(10)),
                                     'notified': dict(trailing_notified.most_common(10))},
            'code_impact': notes}


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
