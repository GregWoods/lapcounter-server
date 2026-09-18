"""Tests for the BLE Layer 1.

paho and bleak are not installed in the test venv (only api/.venv has pytest, and this
container's deps live in its image), so they are stubbed before import. The module only
uses them for I/O, which sits behind an `if __name__ == '__main__'` guard.
"""
import asyncio
import struct
import sys
import types

import pytest


def _stub(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules.setdefault(name, module)


_stub('paho')
_stub('paho.mqtt')
_stub(
    'paho.mqtt.client',
    Client=lambda *a, **k: types.SimpleNamespace(publish=lambda *a, **k: None),
    CallbackAPIVersion=types.SimpleNamespace(VERSION2=2),
)
_stub('bleak', BleakClient=object, BleakScanner=object)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import ble_to_timestamps as ble  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Each test starts disconnected: no seeded cars, no clock anchor."""
    monkeypatch.setattr(ble, '_last_start_finish', [[None, None] for _ in range(6)])
    monkeypatch.setattr(ble, '_clock_offset', None)
    monkeypatch.setattr(ble, '_step_run_since', None)
    monkeypatch.setattr(ble, '_step_run_min', None)
    monkeypatch.setattr(ble, '_timestamps_halted', True)
    monkeypatch.setattr(ble, '_power_retry_at', None)
    monkeypatch.setattr(ble, '_power_retry_delay', ble.POWER_RETRY_INITIAL_DELAY)
    published = []
    monkeypatch.setattr(ble, 'mqtt_client',
                        types.SimpleNamespace(publish=lambda topic, payload: published.append(payload)))
    return published


def packet(car, t1=0, t2=0):
    """An 18-byte Slot notification: seq, car, track1/track2 in raw ticks, pitlane (unused)."""
    return bytearray(bytes([0, car]) + struct.pack('<II', t1, t2) + bytes(8))


def crossings(published):
    import json
    return [(json.loads(p)['car'], json.loads(p)['lane']) for p in published]


def stamps(published):
    import json
    return [json.loads(p)['timestamp'] / 1e9 for p in published]


def ticks(seconds):
    """Device seconds as raw powerbase ticks (10ms on real hardware, see DEVICE_TICK_S)."""
    return round(seconds / ble.DEVICE_TICK_S)


# --------------------------------------------------------------- seeding

def test_first_packet_per_car_seeds_without_publishing(fresh_state):
    """A mid-race reconnect must not turn the powerbase's retained timestamps into laps."""
    for car in range(1, 7):
        ble.handle_slot_notification(None, packet(car, t1=40_000 + car))
    assert crossings(fresh_state) == []


def test_crossing_after_seeding_publishes(fresh_state):
    ble.handle_slot_notification(None, packet(1, t1=40_000))
    ble.handle_slot_notification(None, packet(1, t1=45_000))
    assert crossings(fresh_state) == [(1, 1)]


def test_first_real_lap_after_a_zero_seed_is_not_swallowed(fresh_state):
    """Cold start: timers at zero. The seed must not eat the first genuine crossing."""
    ble.handle_slot_notification(None, packet(3, t1=0, t2=0))
    ble.handle_slot_notification(None, packet(3, t1=5_123))
    assert crossings(fresh_state) == [(3, 1)]


def test_unchanged_repeat_publishes_nothing(fresh_state):
    """The powerbase renotifies full slot state on any field change, not just laps."""
    ble.handle_slot_notification(None, packet(2, t1=10))
    ble.handle_slot_notification(None, packet(2, t1=5_000))
    ble.handle_slot_notification(None, packet(2, t1=5_000))
    assert crossings(fresh_state) == [(2, 1)]


def test_both_tracks_publish_independently(fresh_state):
    ble.handle_slot_notification(None, packet(2, t1=10, t2=20))
    ble.handle_slot_notification(None, packet(2, t1=30, t2=40))
    assert crossings(fresh_state) == [(2, 1), (2, 2)]


@pytest.mark.parametrize('car', [0, 7, 255])
def test_out_of_range_car_id_ignored(fresh_state, car):
    ble.handle_slot_notification(None, packet(car, t1=1))
    assert crossings(fresh_state) == []


def test_short_packet_ignored(fresh_state):
    """Slices truncate silently, so a runt packet would fabricate a lap."""
    ble.handle_slot_notification(None, bytearray(b'\x00\x01\x11\x22'))
    assert crossings(fresh_state) == []
    assert ble._last_start_finish[0] == [None, None]


def test_decode_throttle_layout():
    """20 bytes: seq, six throttles, uint32 throttleTimestamp, isDigital, versions."""
    data = bytearray(bytes([9, 0x3F, 0x40, 0x80, 0, 1, 2]) + struct.pack('<I', 897_122) + bytes(9))
    assert ble.decode_throttle(data) == (897_122, (0x3F, 0x40, 0x80, 0, 1, 2))


def test_decode_throttle_short_packet():
    assert ble.decode_throttle(bytearray(10)) is None


# ------------------------------------------------------- device clock anchoring

def test_slot_timestamps_are_10ms_ticks(fresh_state, monkeypatch):
    """The protocol doc says ms; a real ARC Pro counts 10ms ticks (hardware run,
    2026-09-18). A 3.66s lap arrives as 366, and must publish as 3.66s, not 0.366s,
    which lapdata's MINIMUM_LAP_TIME would silently drop."""
    clock = iter([1000.0, 1000.0, 1003.66])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))
    ble.handle_slot_notification(None, packet(5, t1=0))       # seed
    ble.handle_slot_notification(None, packet(5, t1=1_000))   # 10.00s on the device
    ble.handle_slot_notification(None, packet(5, t1=1_366))   # 13.66s
    t1, t2 = stamps(fresh_state)
    assert t2 - t1 == pytest.approx(3.66, abs=1e-6)



def test_lap_delta_comes_from_the_device_not_arrival(fresh_state, monkeypatch):
    """The whole point: round-robin reporting jitter must not reach lap times.

    Two crossings exactly 5.000s apart on the powerbase clock, reported with wildly
    different delays. The published stamps must still be 5.000s apart.
    """
    clock = iter([1000.0, 1000.2, 1005.9])   # arrival times: 200ms then 900ms late
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))          # seed
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))     # crossing at device 10.000s
    ble.handle_slot_notification(None, packet(1, t1=ticks(15)))     # crossing at device 15.000s

    t1, t2 = stamps(fresh_state)
    assert t2 - t1 == pytest.approx(5.0, abs=1e-6)


def test_anchor_converges_on_the_least_delayed_sample(fresh_state, monkeypatch):
    clock = iter([1000.0, 1010.5, 1020.1])   # 500ms late, then only 100ms late
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))
    assert ble._clock_offset == pytest.approx(1000.5)
    ble.handle_slot_notification(None, packet(1, t1=ticks(20)))
    assert ble._clock_offset == pytest.approx(1000.1)


def test_anchor_never_drifts_upward(fresh_state, monkeypatch):
    """A later, more-delayed sample must not push the anchor back out."""
    clock = iter([1000.0, 1010.1, 1020.9])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))
    ble.handle_slot_notification(None, packet(1, t1=ticks(20)))
    assert ble._clock_offset == pytest.approx(1000.1)


def test_forward_clock_step_reanchors_once_sustained(fresh_state, monkeypatch):
    """Our clock jumps forward an hour (NTP on the Pi; in dev, the host waking from sleep
    while the simulator's monotonic clock stood still). Every sample is now 3600s above
    the anchor, which a running minimum never follows. Once that has held for
    CLOCK_STEP_CONFIRM_S, re-anchor to the least-delayed sample of the run."""
    clock = iter([1000.0, 1010.0, 4620.0, 4623.2, 4625.1])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))           # seed
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))
    assert ble._clock_offset == pytest.approx(1000.0)

    ble.handle_slot_notification(None, packet(1, t1=ticks(20)))      # clock stepped +3600s
    ble.handle_slot_notification(None, packet(1, t1=ticks(23)))      # 3.2s into the run
    assert ble._clock_offset == pytest.approx(1000.0)             # not confirmed yet

    ble.handle_slot_notification(None, packet(1, t1=ticks(25)))      # 5.1s into the run
    assert ble._clock_offset == pytest.approx(4600.0)
    assert stamps(fresh_state)[-1] == pytest.approx(4625.0, abs=0.01)


def test_a_delayed_burst_does_not_move_the_anchor(fresh_state, monkeypatch):
    """A BLE stall delivers a few crossings seconds late, then prompt ones again. Any
    prompt sample ends the run, so two late samples 17s apart never add up to a step."""
    clock = iter([1000.0, 1000.0, 1010.0, 1026.0, 1026.2, 1043.0])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))           # seed car 1
    ble.handle_slot_notification(None, packet(2, t1=0))           # seed car 2
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))      # anchor 1000.0
    ble.handle_slot_notification(None, packet(1, t1=ticks(20)))      # 6s late
    ble.handle_slot_notification(None, packet(2, t1=ticks(26)))      # 0.2s late: ends the run
    ble.handle_slot_notification(None, packet(1, t1=ticks(37)))      # 6s late again, 17s on

    assert ble._clock_offset == pytest.approx(1000.0)


def test_powerbase_timer_reset_reanchors(fresh_state, monkeypatch):
    """Commands 0/1 zero the powerbase timers; a stale anchor would then date every
    crossing to the distant past."""
    clock = iter([1000.0, 1010.0, 1100.0, 1105.0])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))
    assert ble._clock_offset == pytest.approx(1000.0)

    ble.handle_slot_notification(None, packet(1, t1=ticks(0.1)))     # timer went backwards
    ble.handle_slot_notification(None, packet(1, t1=ticks(5.1)))
    published = stamps(fresh_state)
    assert published[-1] == pytest.approx(1105.0, abs=0.01)   # re-anchored to now


def test_power_restored_after_a_halt_reanchors_the_clock(fresh_state, monkeypatch):
    """POWER_ON_TIMER_HALT freezes the powerbase clock. Across a 10s halt the old anchor
    is 10s stale, and a running minimum never corrects it upwards on its own."""
    monkeypatch.setattr(ble, '_timestamps_halted', False)
    clock = iter([1000.0, 1010.0, 1025.05])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))           # seed
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))      # crossing, wall 1010
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)            # halt at device 12s...
    ble._note_command_applied(ble.POWER_ON_RACING)                # ...resumed 10s later
    ble.handle_slot_notification(None, packet(1, t1=ticks(15)))      # 3s after resume, wall 1025

    published = stamps(fresh_state)
    assert published[-1] == pytest.approx(1025.05, abs=0.01)      # not 1015: 10s early


def test_halt_alone_keeps_the_anchor(fresh_state):
    """Crossings reported mid-halt carry the frozen clock, so they only ever sample a
    larger offset — the pre-halt anchor stays the right one until timestamps restart."""
    ble._timestamps_halted = False
    ble._clock_offset = 1000.0
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)
    assert ble._clock_offset == 1000.0


def test_repeated_restart_writes_reanchor_only_once(fresh_state):
    """Resume produces two POWER_ON_RACING writes (race_control and race_state). The
    second must not throw away an anchor rebuilt from real post-resume crossings."""
    ble._note_command_applied(ble.POWER_ON_RACING)
    assert ble._clock_offset is None
    ble._clock_offset = 1000.0
    ble._note_command_applied(ble.POWER_ON_RACING)
    assert ble._clock_offset == 1000.0


# ------------------------------------------------------- 32-bit timer wraparound

UINT32_MAX_TICKS = 2 ** 32 - 1    # ~497 days of 10ms ticks


def test_counter_wrap_is_handled_as_a_reset(fresh_state, monkeypatch):
    """The powerbase's tick counter is uint32, so it wraps ~497 days after its timer
    was last zeroed — and we never send commands 0/1, so it runs from power-on.

    A wrap looks exactly like a timer reset (value jumps backwards), so the reset path
    catches it: re-anchor, and stamp this crossing at arrival. The wrap-spanning lap
    carries arrival-level jitter; every lap after it is clean again.
    """
    clock = iter([1000.0, 1010.0, 1020.0, 1025.0])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=UINT32_MAX_TICKS - ticks(10)))   # seed
    ble.handle_slot_notification(None, packet(1, t1=UINT32_MAX_TICKS - ticks(5)))    # pre-wrap
    ble.handle_slot_notification(None, packet(1, t1=ticks(0.12)))                      # wrapped
    ble.handle_slot_notification(None, packet(1, t1=ticks(5.12)))                    # 5s later

    published = stamps(fresh_state)
    assert published[-2] == pytest.approx(1020.0, abs=0.01)   # stamped at arrival
    # and normal device-accurate timing resumes immediately afterwards
    assert published[-1] - published[-2] == pytest.approx(5.0, abs=1e-6)


def test_wrap_does_not_emit_a_time_in_the_distant_past(fresh_state, monkeypatch):
    """Without re-anchoring, a wrapped value against a pre-wrap anchor would date the
    crossing ~497 days ago. lapdata would reject that outright."""
    clock = iter([1000.0, 1010.0, 1020.0])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=UINT32_MAX_TICKS - ticks(10)))
    ble.handle_slot_notification(None, packet(1, t1=UINT32_MAX_TICKS - ticks(5)))
    ble.handle_slot_notification(None, packet(1, t1=ticks(0.12)))

    assert stamps(fresh_state)[-1] > 1000.0    # not ~497 days in the past


# ------------------------------------------------------------ device discovery

@pytest.mark.parametrize('name, expected', [
    ('Scalextric ARC  ', True),    # the spec's actual advertised name, two trailing spaces
    ('Scalextric ARC', True),
    ('Scalextric ARC PRO', True),
    ('Fitbit Charge', False),
    ('', False),
    (None, False),
])
def test_name_matching(name, expected):
    device = types.SimpleNamespace(name=name)
    assert ble._name_matches(device, types.SimpleNamespace(local_name=None)) is expected


def test_name_falls_back_to_advertisement_local_name():
    """bleak >= 1.0 returns None for an uncached name."""
    device = types.SimpleNamespace(name=None)
    adv = types.SimpleNamespace(local_name='Scalextric ARC  ')
    assert ble._name_matches(device, adv) is True


# ------------------------------------------------------ race lifecycle / power

def sent_commands(monkeypatch):
    """Patch send_command to record byte-0 command codes instead of writing GATT."""
    sent = []
    monkeypatch.setattr(ble, 'send_command', lambda command: sent.append(command))
    return sent


@pytest.mark.parametrize('command', ['prepare', 'arm', 'start', 'yellow', 'resume', 'end'])
def test_race_control_keeps_full_power(monkeypatch, command):
    sent = sent_commands(monkeypatch)
    ble.handle_race_control({'command': command})
    assert sent == [ble.POWER_ON_RACING]


def test_race_control_pause_sends_timer_halt(monkeypatch):
    """'pause' is the no-grace immediate stop, distinct from 'yellow'."""
    sent = sent_commands(monkeypatch)
    ble.handle_race_control({'command': 'pause'})
    assert sent == [ble.POWER_ON_TIMER_HALT]


def test_race_control_status_sends_nothing(monkeypatch):
    sent = sent_commands(monkeypatch)
    ble.handle_race_control({'command': 'status'})
    assert sent == []


def test_race_state_paused_sends_timer_halt(monkeypatch):
    """The Yellow -> Paused grace-expiry transition is only ever announced via
    race_state (lapdata drives it with an internal timer, not a race_control
    message), so this is the only place that can react to it."""
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Yellow')
    sent = sent_commands(monkeypatch)
    ble.handle_race_state({'state': 'Paused'})
    assert sent == [ble.POWER_ON_TIMER_HALT]
    assert ble._last_seen_race_state == 'Paused'


def test_race_state_yellow_keeps_full_power(monkeypatch):
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Running')
    sent = sent_commands(monkeypatch)
    ble.handle_race_state({'state': 'Yellow'})
    assert sent == [ble.POWER_ON_RACING]


def test_race_state_repeated_same_state_does_not_resend(monkeypatch):
    """race_state republishes on every lap crossing — a write per message would
    spam the powerbase with redundant GATT writes."""
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Running')
    sent = sent_commands(monkeypatch)
    ble.handle_race_state({'state': 'Running'})
    assert sent == []


@pytest.mark.parametrize('state, expected', [
    ('Paused', ble.POWER_ON_TIMER_HALT),
    ('Yellow', ble.POWER_ON_RACING),
    ('Running', ble.POWER_ON_RACING),
    ('Finished', ble.POWER_ON_RACING),
    ('NotStarted', ble.POWER_ON_RACING),
    (None, ble.POWER_ON_RACING),
])
def test_connect_time_power_follows_the_race(state, expected):
    """run() writes this on every BLE connect. Always POWER_ON_RACING would restore
    power to a Paused race after a reconnect, since the Paused edge was already seen."""
    assert ble._command_for_race_state(state) == expected


def test_mqtt_connect_asks_lapdata_for_race_state():
    """race_state isn't retained: after a container restart, this is how BLE learns the
    race is Paused before its connect-time power write."""
    import json
    published = []
    client = types.SimpleNamespace(
        subscribe=lambda topic: None,
        publish=lambda topic, payload: published.append((topic, json.loads(payload))),
    )
    ble.on_mqtt_connect(client, None, None, None, None)
    assert ('race_control', {'command': 'status'}) in published


class FakeBleakClient:
    is_connected = True

    def __init__(self, fail=False):
        self.fail = fail
        self.written = []

    async def write_gatt_char(self, _uuid, payload):
        if self.fail:
            raise RuntimeError('GATT write rejected')
        self.written.append(payload[0])


def test_failed_power_write_is_retried_with_the_current_race_state(monkeypatch):
    """Never the command that failed: it may be stale by the time the retry runs, and
    a retried HALT landing after a resume would cut power on a running race."""
    client = FakeBleakClient(fail=True)
    monkeypatch.setattr(ble, '_bleak_client', client)
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Paused')
    asyncio.run(ble._write_command_async(ble.POWER_ON_TIMER_HALT))
    assert ble._power_retry_at is not None

    ble._last_seen_race_state = 'Running'     # operator resumed in the meantime
    client.fail = False
    ble._power_retry_at = 0.0                 # due now
    asyncio.run(ble._retry_power_if_due())

    assert client.written == [ble.POWER_ON_RACING]
    assert ble._power_retry_at is None


def test_retry_waits_until_it_is_due(monkeypatch):
    client = FakeBleakClient()
    monkeypatch.setattr(ble, '_bleak_client', client)
    monkeypatch.setattr(ble, '_power_retry_at', float('inf'))
    asyncio.run(ble._retry_power_if_due())
    assert client.written == []


def test_retry_backs_off_to_a_cap(monkeypatch):
    """A powerbase with no Command characteristic (ARC One) rejects every write."""
    monkeypatch.setattr(ble, '_bleak_client', FakeBleakClient(fail=True))
    delays = []
    for _ in range(8):
        before = ble.time.monotonic()
        asyncio.run(ble._write_command_async(ble.POWER_ON_RACING))
        delays.append(round(ble._power_retry_at - before))
    assert delays == [1, 2, 4, 8, 16, 30, 30, 30]


# --------------------------------------------------------- command payload

def test_command_payload_layout():
    """Bytes 1-6 are a POWER MULTIPLIER, not padding — zeros mean no car moves."""
    payload = ble.command_payload(ble.POWER_ON_RACING)
    assert len(payload) == 20
    assert payload[0] == 3
    assert list(payload[1:7]) == [0x3F] * 6      # full throttle pass-through
    assert payload[1] & 0x80 == 0                # direct-drive override bit clear
    assert list(payload[7:20]) == [0] * 13       # rumble/brake/KERS genuinely unused
