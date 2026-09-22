"""Tests for the BLE Layer 1.

paho and bleak are not installed in the test venv (only api/.venv has pytest, and this
container's deps live in its image), so they are stubbed before import. The module only
uses them for I/O, which sits behind an `if __name__ == '__main__'` guard.
"""
import asyncio
import importlib
import json
import re
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
    """Each test starts disconnected: no seeded cars, a clock of its own."""
    monkeypatch.setattr(ble, '_last_start_finish', [[None, None] for _ in range(6)])
    monkeypatch.setattr(ble, '_baseline_clock', [None] * 6)
    monkeypatch.setattr(ble, '_timestamps_halted', True)
    monkeypatch.setattr(ble, '_last_heartbeat_at', None)
    monkeypatch.setattr(ble, '_power_retry_at', None)
    monkeypatch.setattr(ble, '_power_retry_delay', ble.POWER_RETRY_INITIAL_DELAY)
    published = []
    monkeypatch.setattr(ble, 'mqtt_client', types.SimpleNamespace(
        publish=lambda topic, payload: published.append((topic, json.loads(payload)))))
    ble._new_clock('test setup')
    return published


def packet(car, t1=0, t2=0):
    """An 18-byte Slot notification: seq, car, track1/track2 in raw ticks, pitlane (unused)."""
    return bytearray(bytes([0, car]) + struct.pack('<II', t1, t2) + bytes(8))


def throttle_packet(timestamp_ticks, throttles=(0,) * 6):
    """A 20-byte Throttle notification: seq, six throttle bytes, uint32 throttleTimestamp,
    then isDigital and firmware versions, which this project never reads."""
    return bytearray(bytes([0]) + bytes(throttles)
                     + struct.pack('<I', timestamp_ticks) + bytes(9))


def _of(published, topic):
    return [p for t, p in published if t == topic]


def crossings(published):
    return [(p['car'], p['lane']) for p in _of(published, ble.MQTT_TIMESTAMP_TOPIC)]


def counters(published):
    return [p['counter_ms'] for p in _of(published, ble.MQTT_TIMESTAMP_TOPIC)]


def clocks(published):
    return [p['clock'] for p in _of(published, ble.MQTT_TIMESTAMP_TOPIC)]


def heartbeats(published):
    return _of(published, ble.MQTT_CLOCK_TOPIC)


def ticks(seconds):
    """Device seconds as raw powerbase ticks (10ms on real hardware, see DEVICE_TICK_S)."""
    return round(seconds / ble.DEVICE_TICK_S)


# --------------------------------------------------------------- seeding

def test_first_packet_per_car_seeds_without_publishing(fresh_state):
    """A mid-race reconnect must not turn the powerbase's retained timestamps into laps."""
    for car in range(1, 7):
        ble.handle_slot_notification(None, packet(car, t1=40_000 + car))
    assert crossings(fresh_state) == []


def _reconnect():
    """What run() does on reconnect: a new clock, and the per-car baselines KEPT."""
    ble._new_clock('reconnected to the powerbase')


def test_a_crossing_made_while_disconnected_is_still_counted(fresh_state):
    """⚠️ Regression (Greg, 2026-09-20): "those crossings are real laps". The powerbase
    reports each car's last crossing as absolute state, so one made while the link was
    down is still there when we reconnect — and clearing the baselines used to throw it
    away as a fresh seed. A power cycle mid-race cost two laps that way."""
    ble.handle_slot_notification(None, packet(1, t1=ticks(50)))    # first connect: seed
    _reconnect()
    ble.handle_slot_notification(None, packet(1, t1=ticks(58)))    # crossed while away

    assert crossings(fresh_state) == [(1, 1)]
    assert counters(fresh_state) == [58_000]
    # On the CURRENT clock: its anchor is derived from whichever counter the powerbase is
    # running now, and this stamp came from that same counter.
    assert clocks(fresh_state) == [ble._clock]


def test_a_reconnect_with_nothing_crossed_publishes_nothing(fresh_state):
    """The other half of keeping the baselines: an unchanged stamp is not a lap. This is
    what stops six phantom laps on every reconnect."""
    ble.handle_slot_notification(None, packet(1, t1=ticks(50)))
    ble.handle_slot_notification(None, packet(1, t1=ticks(60)))    # a real lap
    before = len(crossings(fresh_state))

    _reconnect()
    ble.handle_slot_notification(None, packet(1, t1=ticks(60)))    # same stamp as before
    assert len(crossings(fresh_state)) == before


def test_a_crossing_after_a_power_cycle_but_before_we_reconnect_is_counted(fresh_state):
    """The timers are zeroed by a power cycle, so a SMALLER stamp than we remember means
    the powerbase rebooted — and a non-zero one is a real crossing since power-up."""
    ble.handle_slot_notification(None, packet(1, t1=ticks(500)))   # seed, long-running base
    _reconnect()
    clock_after_reconnect = ble._clock
    ble.handle_slot_notification(None, packet(1, t1=ticks(3)))     # zeroed, then crossed

    assert crossings(fresh_state) == [(1, 1)]
    assert counters(fresh_state) == [3_000]
    # ⚠️ And only ONE clock for the reset: backwards-detection must not fire on top of the
    # reconnect's own new clock, or each of the six cars would start another in turn.
    assert ble._clock == clock_after_reconnect


def test_a_power_cycle_with_no_crossing_yet_publishes_nothing(fresh_state):
    """Every car reports 0 after a power cycle until it crosses. Zero is not a lap."""
    ble.handle_slot_notification(None, packet(1, t1=ticks(500)))
    _reconnect()
    ble.handle_slot_notification(None, packet(1, t1=0))
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


# ---------------------------------------------------- the counter/clock contract

def test_crossing_carries_the_raw_counter_and_the_clock(fresh_state):
    """No conversion to anyone's wall clock: the powerbase's own number, plus the clock
    it is meaningful on. lapdata subtracts two of these to get a lap time."""
    ble.handle_slot_notification(None, packet(5, t1=0))           # seed
    ble.handle_slot_notification(None, packet(5, t1=1_366))       # device 13.66s

    assert counters(fresh_state) == [13_660]
    assert clocks(fresh_state) == [ble._clock]


def test_counter_is_10ms_ticks_not_milliseconds(fresh_state):
    """The protocol doc says ms; a real ARC Pro counts 10ms ticks (hardware run,
    2026-09-18). Read as ms, every lap came out 10x short and fell under lapdata's
    MINIMUM_LAP_TIME — i.e. no laps at all."""
    ble.handle_slot_notification(None, packet(5, t1=0))
    ble.handle_slot_notification(None, packet(5, t1=1_000))       # 10.00s on the device
    ble.handle_slot_notification(None, packet(5, t1=1_366))       # 13.66s

    a, b = counters(fresh_state)
    assert (b - a) / 1000 == pytest.approx(3.66, abs=1e-9)


def test_clock_ids_are_never_reused_within_a_process(fresh_state):
    seen = {ble._new_clock('test') for _ in range(50)}
    assert len(seen) == 50


def test_clock_ids_differ_between_processes():
    """A restarted ble container must not publish an id the previous process used, or
    lapdata would compare its counters against the dead process's. Reloading the module
    re-runs the secrets.token_hex() at import, which is exactly what a restart does."""
    before = ble._PROCESS_ID
    try:
        importlib.reload(ble)
        assert ble._PROCESS_ID != before
        assert re.fullmatch(r'ble:[0-9a-f]{6}:\d+', ble._clock)
    finally:
        importlib.reload(ble)


# --- A new clock on every event that breaks the counter ---

def test_a_backwards_value_starts_a_new_clock(fresh_state):
    """Commands 0/1 and a power cycle zero the powerbase timers. Counters either side of
    that can't be subtracted, so they must not share a clock."""
    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))
    before = ble._clock

    ble.handle_slot_notification(None, packet(1, t1=ticks(0.1)))   # went backwards
    assert ble._clock != before
    assert clocks(fresh_state) == [before, ble._clock]


def test_a_reset_starts_exactly_one_clock_across_all_six_cars(fresh_state):
    """A reset zeroes all six cars, and their zeroed packets arrive one at a time over
    the next rotation. Without the per-car baseline clock, each would read as another
    backwards jump: six clocks for one reset, and every lap spanning any of them
    downgraded from an exact counter subtraction to an anchored one."""
    for car in range(1, 7):
        ble.handle_slot_notification(None, packet(car, t1=ticks(10)))   # seed
    before = ble._clock

    for car in range(1, 7):
        ble.handle_slot_notification(None, packet(car, t1=0))           # all zeroed

    assert ble._clock != before
    assert int(ble._clock.rsplit(':', 1)[1]) == int(before.rsplit(':', 1)[1]) + 1


def test_a_crossing_after_a_reset_publishes_on_the_new_clock(fresh_state):
    """The baseline is still compared across the reset — the value changed, so the car
    really did cross — but the crossing belongs to the new clock."""
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))    # seed
    ble.handle_slot_notification(None, packet(1, t1=0))            # reset, no crossing
    new_clock = ble._clock
    ble.handle_slot_notification(None, packet(1, t1=ticks(3)))     # first lap after reset

    assert crossings(fresh_state) == [(1, 1)]
    assert clocks(fresh_state) == [new_clock]
    assert counters(fresh_state) == [3_000]


def test_a_halting_write_starts_a_new_clock(fresh_state):
    """⚠️ The easy one to miss: a halting command freezes the counter WITHOUT moving it
    backwards, so the backwards-detection can never catch it. A D-second halt leaves the
    counter D behind real time forever.

    ble no longer sends one — a yellow flag stops the cars with CARS_STOPPED, which leaves
    the counter running — but the safety net has to work if one arrives another way."""
    ble._timestamps_halted = False
    before = ble._clock
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)
    assert ble._clock != before


def test_a_restarting_write_starts_a_new_clock(fresh_state):
    ble._timestamps_halted = True
    before = ble._clock
    ble._note_command_applied(ble.POWER_ON_RACING)
    assert ble._clock != before


def test_a_halt_and_resume_starts_two_clocks(fresh_state):
    """Both ends matter. At the halt, so heartbeat samples reported during it (the
    counter frozen, arrivals advancing) land on a throwaway clock instead of corrupting
    the anchor that pre-halt laps were timed on. At the resume, for the offset."""
    ble._timestamps_halted = False
    start = ble._clock
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)
    halted = ble._clock
    ble._note_command_applied(ble.POWER_ON_RACING)
    assert len({start, halted, ble._clock}) == 3


def test_repeated_racing_writes_do_not_start_a_clock(fresh_state):
    """Resume produces two POWER_ON_RACING writes (race_control and race_state), and
    race_state re-sends on several transitions. The counter never stopped, so nothing is
    discontinuous — burning a clock would needlessly downgrade the lap in progress."""
    ble._timestamps_halted = True
    ble._note_command_applied(ble.POWER_ON_RACING)
    after_first = ble._clock
    ble._note_command_applied(ble.POWER_ON_RACING)
    ble._note_command_applied(ble.POWER_ON_RACING)
    assert ble._clock == after_first


def test_repeated_halting_writes_do_not_start_a_clock(fresh_state):
    ble._timestamps_halted = False
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)
    after_first = ble._clock
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)
    assert ble._clock == after_first


# --- 32-bit timer wraparound ---

UINT32_MAX_TICKS = 2 ** 32 - 1    # ~497 days of 10ms ticks


def test_counter_wrap_starts_a_new_clock(fresh_state):
    """The tick counter is uint32, so it wraps ~497 days after its timer was last
    zeroed — and we never send commands 0/1, so it runs from power-on. Handling the wrap
    is Layer 1's job: it reads as the counter going backwards, which is a new clock, so
    lapdata never has to know about it."""
    ble.handle_slot_notification(None, packet(1, t1=UINT32_MAX_TICKS - ticks(10)))  # seed
    ble.handle_slot_notification(None, packet(1, t1=UINT32_MAX_TICKS - ticks(5)))
    before = ble._clock

    ble.handle_slot_notification(None, packet(1, t1=ticks(0.12)))                   # wrapped
    assert ble._clock != before

    ble.handle_slot_notification(None, packet(1, t1=ticks(5.12)))
    post_wrap = counters(fresh_state)[-2:]
    assert (post_wrap[1] - post_wrap[0]) / 1000 == pytest.approx(5.0, abs=1e-9)


# --- The Throttle clock heartbeat (plan A) ---

def test_throttle_notification_publishes_a_clock_sample(fresh_state):
    """This is what makes lap 1 accurate: crossings anchor the clock too, but a car has
    to cross first, and lap 1 is timed from lights-out before any car has."""
    ble.handle_throttle_notification(None, throttle_packet(ticks(12.34)))
    assert heartbeats(fresh_state) == [{'clock': ble._clock, 'counter_ms': 12_340}]


def test_the_heartbeat_uses_the_slot_clock(fresh_state):
    """HW-12 (2026-09-20) measured throttleTimestamp to be a live reading of the same
    clock the Slot crossings are stamped on, so samples from it anchor that clock.
    ⚠️ If a later firmware keeps throttle on its own clock, these must carry their own
    clock id — a heartbeat from a different clock with a smaller offset would silently
    drag lapdata's anchor down, and a running minimum cannot notice that."""
    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=ticks(10)))
    ble.handle_throttle_notification(None, throttle_packet(ticks(10.5)))
    assert heartbeats(fresh_state)[0]['clock'] == clocks(fresh_state)[0]


def test_the_heartbeat_follows_a_clock_change(fresh_state):
    ble._timestamps_halted = False
    ble.handle_throttle_notification(None, throttle_packet(ticks(10)))
    ble._note_command_applied(ble.POWER_ON_TIMER_HALT)
    ble._last_heartbeat_at = None                      # past the rate limit
    ble.handle_throttle_notification(None, throttle_packet(ticks(12)))

    first, second = heartbeats(fresh_state)
    assert first['clock'] != second['clock'] == ble._clock


def test_the_heartbeat_is_rate_limited(fresh_state, monkeypatch):
    """Bounds a future firmware that notifies faster than the measured 3.3/s. Publishing
    promptly and dropping the excess beats buffering a window: buffering would hold every
    sample back before lapdata could stamp its arrival, and lateness is the only thing
    that degrades the anchor."""
    now = [1000.0]
    monkeypatch.setattr(ble.time, 'monotonic', lambda: now[0])

    ble.handle_throttle_notification(None, throttle_packet(ticks(10)))
    now[0] += ble.HEARTBEAT_MIN_INTERVAL_S / 2
    ble.handle_throttle_notification(None, throttle_packet(ticks(10.05)))
    assert len(heartbeats(fresh_state)) == 1

    now[0] += ble.HEARTBEAT_MIN_INTERVAL_S
    ble.handle_throttle_notification(None, throttle_packet(ticks(10.15)))
    assert len(heartbeats(fresh_state)) == 2


def test_a_short_throttle_packet_publishes_nothing(fresh_state):
    ble.handle_throttle_notification(None, bytearray(10))
    assert heartbeats(fresh_state) == []


def test_the_heartbeat_can_be_turned_off(fresh_state, monkeypatch):
    """BLE_CLOCK_HEARTBEAT=none falls back to anchoring from crossings alone (plan C)."""
    monkeypatch.setattr(ble, 'clock_heartbeat', 'none')
    subscribed = []

    class Client:
        async def start_notify(self, uuid, _cb):
            subscribed.append(uuid)

    asyncio.run(ble._subscribe_clock_heartbeat(Client()))
    assert subscribed == []


def test_a_powerbase_that_refuses_throttle_still_counts_laps(fresh_state, monkeypatch):
    """An ARC One has no such characteristic. Losing the heartbeat costs a less accurate
    lap 1, and must never tear down the slot subscription that is this container's job."""
    monkeypatch.setattr(ble, 'clock_heartbeat', 'throttle')

    class Client:
        async def start_notify(self, _uuid, _cb):
            raise RuntimeError('Characteristic was not found!')

    asyncio.run(ble._subscribe_clock_heartbeat(Client()))   # must not raise

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=ticks(5)))
    assert crossings(fresh_state) == [(1, 1)]


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
    """Patch send_command to record PowerStates instead of writing GATT."""
    sent = []
    monkeypatch.setattr(ble, 'send_command', lambda state: sent.append(state))
    return sent


@pytest.mark.parametrize('command', ['prepare', 'arm', 'start', 'yellow', 'resume', 'end'])
def test_race_control_keeps_full_power(monkeypatch, command):
    sent = sent_commands(monkeypatch)
    ble.handle_race_control({'command': command})
    assert sent == [ble.TRACK_RACING]


def test_race_control_pause_stops_the_cars(monkeypatch):
    """'pause' is the no-grace immediate stop, distinct from 'yellow'."""
    sent = sent_commands(monkeypatch)
    ble.handle_race_control({'command': 'pause'})
    assert sent == [ble.CARS_STOPPED]


def test_race_control_status_sends_nothing(monkeypatch):
    sent = sent_commands(monkeypatch)
    ble.handle_race_control({'command': 'status'})
    assert sent == []


def test_race_state_paused_stops_the_cars(monkeypatch):
    """The Yellow -> Paused grace-expiry transition is only ever announced via
    race_state (lapdata drives it with an internal timer, not a race_control
    message), so this is the only place that can react to it."""
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Yellow')
    sent = sent_commands(monkeypatch)
    ble.handle_race_state({'state': 'Paused'})
    assert sent == [ble.CARS_STOPPED]
    assert ble._last_seen_race_state == 'Paused'


def test_stopping_the_cars_leaves_the_counter_running(monkeypatch):
    """⚠️ The whole reason CARS_STOPPED is a zero multiplier rather than command 4: a
    stoppage must not break the counter, so the lap spanning a yellow flag stays an exact
    counter subtraction (one long lap, the stopped time included) instead of going through
    lapdata's anchor. Both states BEING command 3 is the point, not an accident."""
    assert ble.CARS_STOPPED.command == ble.POWER_ON_RACING == ble.TRACK_RACING.command
    assert ble.CARS_STOPPED.command not in ble._TIMESTAMP_BREAKING_COMMANDS
    assert ble.CARS_STOPPED.power == 0

    ble._timestamps_halted = False
    before = ble._clock
    ble._note_command_applied(ble.CARS_STOPPED.command)
    assert ble._clock == before


def test_race_state_yellow_keeps_full_power(monkeypatch):
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Running')
    sent = sent_commands(monkeypatch)
    ble.handle_race_state({'state': 'Yellow'})
    assert sent == [ble.TRACK_RACING]


def test_race_state_repeated_same_state_does_not_resend(monkeypatch):
    """race_state republishes on every lap crossing — a write per message would
    spam the powerbase with redundant GATT writes."""
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Running')
    sent = sent_commands(monkeypatch)
    ble.handle_race_state({'state': 'Running'})
    assert sent == []


@pytest.mark.parametrize('state, expected', [
    ('Paused', ble.CARS_STOPPED),
    ('Yellow', ble.TRACK_RACING),
    ('Running', ble.TRACK_RACING),
    ('Finished', ble.TRACK_RACING),
    ('NotStarted', ble.TRACK_RACING),
    (None, ble.TRACK_RACING),
])
def test_connect_time_power_follows_the_race(state, expected):
    """run() writes this on every BLE connect. Always TRACK_RACING would set cars moving
    on a Paused race after a reconnect, since the Paused edge was already seen."""
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
        # Byte 0 alone no longer identifies the write: racing and stopped are both
        # command 3, told apart only by the multiplier in bytes 1-6.
        self.written.append(ble.PowerState(payload[0], payload[1]))


def test_failed_power_write_is_retried_with_the_current_race_state(monkeypatch):
    """Never the command that failed: it may be stale by the time the retry runs, and
    a retried HALT landing after a resume would cut power on a running race."""
    client = FakeBleakClient(fail=True)
    monkeypatch.setattr(ble, '_bleak_client', client)
    monkeypatch.setattr(ble, '_last_seen_race_state', 'Paused')
    asyncio.run(ble._write_command_async(ble.CARS_STOPPED))
    assert ble._power_retry_at is not None

    ble._last_seen_race_state = 'Running'     # operator resumed in the meantime
    client.fail = False
    ble._power_retry_at = 0.0                 # due now
    asyncio.run(ble._retry_power_if_due())

    assert client.written == [ble.TRACK_RACING]
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
        asyncio.run(ble._write_command_async(ble.TRACK_RACING))
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


def test_stopped_payload_zeroes_every_multiplier():
    """What actually stops the cars under a yellow flag. hardware_check.py wants full
    power and never passes one, hence the default — so a zero has to be explicit."""
    payload = ble.command_payload(*ble.CARS_STOPPED)
    assert payload[0] == 3                       # still racing, so the counter runs on
    assert list(payload[1:7]) == [0] * 6         # ...but no car can move
    assert list(ble.command_payload(ble.POWER_ON_RACING)[1:7]) == [0x3F] * 6
