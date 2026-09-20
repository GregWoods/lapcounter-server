"""Tests for lapdata's handling of Layer 1 crossings on the counter contract.

paho is not installed in the test venv, so it is stubbed before import. The module only
uses it for I/O, which sits behind an `if __name__ == '__main__'` guard.
"""
import json
import sys
import threading
import time
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
    Client=lambda *a, **k: types.SimpleNamespace(
        publish=lambda *a, **k: None, on_connect=None, on_message=None,
    ),
    CallbackAPIVersion=types.SimpleNamespace(VERSION2=2),
)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import timestamps_to_lapdata as tsl  # noqa: E402
from lap_clock import ClockAnchors, Crossing  # noqa: E402

CLOCK = 'ble:aa11bb:1'


@pytest.fixture
def published(monkeypatch):
    """Capture MQTT publishes, and give each test a clean anchor set and phantom filter."""
    sent = []
    monkeypatch.setattr(tsl, 'client', types.SimpleNamespace(
        publish=lambda topic, payload: sent.append((topic, json.loads(payload)))))
    monkeypatch.setattr(tsl, 'anchors', ClockAnchors())
    monkeypatch.setattr(tsl, 'prev_crossing', [None] * 6)
    monkeypatch.setattr(tsl.race, 'on_lap', lambda lane, crossing: False)
    return sent


def _laps(sent):
    return [p for topic, p in sent if topic == 'lap']


def _msg(topic, payload):
    return types.SimpleNamespace(topic=topic, payload=json.dumps(payload).encode())


def _crossing(car, counter_ms, clock=CLOCK):
    return {'car': car, 'lane': 1, 'counter_ms': counter_ms, 'clock': clock}


# --- The old contract is rejected outright, not guessed at ---

@pytest.mark.parametrize('payload', [
    {'car': 1, 'lane': 1, 'timestamp': 1_700_000_000_000_000_000},   # the old format
    {'car': 1, 'lane': 1, 'counter_ms': 5000},                       # no clock
    {'car': 1, 'lane': 1, 'clock': CLOCK},                           # no counter
    {'car': 1, 'lane': 1, 'counter_ms': -1, 'clock': CLOCK},
    {'car': 1, 'lane': 1, 'counter_ms': '5000', 'clock': CLOCK},
    {'car': 1, 'lane': 1, 'counter_ms': True, 'clock': CLOCK},       # bool is an int
    {'car': 1, 'lane': 1, 'counter_ms': 5000, 'clock': ''},
])
def test_an_old_or_malformed_car_timestamp_is_dropped_with_an_error(published, caplog, payload):
    """Decision 4: the contract changes in one step, with no fallback. A Layer 1 image
    older than lapdata would otherwise publish laps that look plausible and are timed on
    a different basis — worse at a meet than counting nothing and saying why."""
    tsl.handle_car_timestamp(payload, arrival=1000.0)
    assert _laps(published) == []
    assert 'older than lapdata' in caplog.text


# --- Lap timing comes from the counter, never from arrival ---

def test_lap_time_comes_from_counter_deltas_not_arrival(published):
    """Two crossings 5.000s apart on Layer 1's counter, delivered with very different
    latency, still measure 5.000s."""
    tsl.handle_car_timestamp(_crossing(1, 10_000), arrival=1010.1)   # 100ms late
    tsl.handle_car_timestamp(_crossing(1, 15_000), arrival=1015.9)   # 900ms late
    assert _laps(published)[-1]['lapTime'] == pytest.approx(5.0)


def test_first_crossing_of_a_race_reports_no_lap_time(published):
    """There is genuinely no interval to report. The old code seeded a previous crossing
    time and invented one."""
    tsl.handle_car_timestamp(_crossing(1, 10_000), arrival=1010.0)
    assert _laps(published)[0]['lapTime'] is None


def test_phantom_filter_works_on_counters(published, monkeypatch):
    """Two crossings closer together than MINIMUM_LAP_TIME on Layer 1's counter are a
    phantom trigger even when latency spread their arrivals much further apart — which
    is exactly what a Slot rotation does."""
    monkeypatch.setattr(tsl, 'min_lap_time_s', 4.0)
    tsl.handle_car_timestamp(_crossing(1, 10_000), arrival=1010.0)
    tsl.handle_car_timestamp(_crossing(1, 11_000), arrival=1020.0)   # 1s later, 10s apart
    assert len(_laps(published)) == 1


def test_a_genuine_lap_is_not_filtered_by_a_late_notification(published, monkeypatch):
    """The mirror case, and the one that loses a real lap: a delayed notification must
    not be able to push two genuine crossings under MINIMUM_LAP_TIME."""
    monkeypatch.setattr(tsl, 'min_lap_time_s', 4.0)
    tsl.handle_car_timestamp(_crossing(1, 10_000), arrival=1010.0)
    tsl.handle_car_timestamp(_crossing(1, 15_000), arrival=1010.2)   # arrived 200ms apart
    assert len(_laps(published)) == 2


def test_lanes_are_filtered_independently(published, monkeypatch):
    monkeypatch.setattr(tsl, 'min_lap_time_s', 4.0)
    tsl.handle_car_timestamp(_crossing(1, 10_000), arrival=1010.0)
    tsl.handle_car_timestamp(_crossing(2, 10_100), arrival=1010.1)
    assert len(_laps(published)) == 2


def test_a_crossing_feeds_the_clock_anchor(published):
    tsl.handle_car_timestamp(_crossing(1, 10_000), arrival=1010.0)
    assert tsl.anchors.offset(CLOCK) == pytest.approx(1000.0)


# --- driver_lap provenance ---

def test_driver_lap_carries_the_clock_counter_and_timing(published, monkeypatch):
    """The only way to re-check a disputed lap after the meet is to know which clock
    timed it and how."""
    driver = types.SimpleNamespace(driver_id=9, laps_completed=0, lap_times=[],
                                   last_lap_timing='')

    def count_a_lap(lane, crossing):
        driver.laps_completed += 1
        driver.lap_times.append(4.5)
        driver.last_lap_timing = 'counter'
        return True

    monkeypatch.setattr(tsl.race, 'on_lap', count_a_lap)
    monkeypatch.setattr(tsl.race, 'drivers', {1: driver})
    monkeypatch.setattr(tsl, 'publish_race_state', lambda: None)

    tsl.handle_car_timestamp(_crossing(1, 12_340), arrival=1012.4)

    lap = next(p for topic, p in published if topic == 'driver_lap')
    assert lap['clock'] == CLOCK
    assert lap['counter_ms'] == 12_340
    assert lap['timing'] == 'counter'
    assert lap['lap_time'] == pytest.approx(4.5)


# --- layer1_clock heartbeat ---

def test_layer1_clock_feeds_the_anchor():
    """This is what makes lap 1 accurate: crossings anchor the clock too, but only once
    a car has crossed, and lap 1 is timed from lights-out before any of that."""
    anchors = ClockAnchors()
    tsl.anchors, saved = anchors, tsl.anchors
    try:
        tsl.handle_layer1_clock({'clock': CLOCK, 'counter_ms': 9_000}, arrival=1009.05)
        assert anchors.offset(CLOCK) == pytest.approx(1000.05)
    finally:
        tsl.anchors = saved


@pytest.mark.parametrize('payload', [
    {'counter_ms': 9_000}, {'clock': CLOCK}, {'clock': CLOCK, 'counter_ms': -1},
    {'clock': '', 'counter_ms': 9_000}, {'clock': CLOCK, 'counter_ms': 'x'},
])
def test_a_malformed_heartbeat_is_ignored_quietly(payload):
    """Unlike a crossing, these arrive several times a second — a bad one must not flood
    the log, and dropping it costs only a little anchor accuracy."""
    anchors = ClockAnchors()
    tsl.anchors, saved = anchors, tsl.anchors
    try:
        tsl.handle_layer1_clock(payload, arrival=1009.0)
        assert anchors.offset(payload.get('clock') or CLOCK) is None
    finally:
        tsl.anchors = saved


# --- Timing values are taken before the race lock ---

def _run_while_lock_is_held(target, hold_for=0.2):
    """Run `target` on a worker thread while _race_lock is held elsewhere, so anything
    it stamps *after* acquiring the lock is late by `hold_for`."""
    got_lock = threading.Event()
    release = threading.Event()

    def hold():
        with tsl._race_lock:
            got_lock.set()
            release.wait(5)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert got_lock.wait(5)

    before = time.monotonic()
    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    time.sleep(hold_for)
    release.set()
    worker.join(5)
    holder.join(5)
    return before


def test_arrival_is_stamped_before_the_race_lock(monkeypatch):
    """The anchor is a running minimum of (arrival - counter), so time spent waiting for
    the lock would look like transport delay and degrade every anchor behind it."""
    captured = []
    monkeypatch.setattr(tsl, 'handle_car_timestamp',
                        lambda data, arrival: captured.append(arrival))

    before = _run_while_lock_is_held(
        lambda: tsl.on_message(None, None, _msg('car_timestamp', _crossing(1, 10_000))))

    assert captured, 'handler never ran'
    assert captured[0] - before < 0.1


def test_lights_out_takes_its_instant_before_the_race_lock(monkeypatch):
    """Every lap 1 in the race is timed from this value."""
    captured = []
    monkeypatch.setattr(tsl.race, 'state', 'ArmedForStart')
    monkeypatch.setattr(tsl.race, 'start', lambda go=None: captured.append(go))
    monkeypatch.setattr(tsl, '_schedule_end_timer', lambda: None)
    monkeypatch.setattr(tsl, 'publish_race_state', lambda: None)
    monkeypatch.setattr(tsl, 'fetch_pending_race', lambda: None)

    before = _run_while_lock_is_held(tsl._lights_out(tsl._start_generation))

    assert captured, 'lights-out never ran'
    assert captured[0] - before < 0.1


def test_lights_out_clears_the_phantom_filter(monkeypatch):
    """No phantom laps bleed across a race start, and the first crossing of the new race
    is never filtered."""
    monkeypatch.setattr(tsl.race, 'state', 'ArmedForStart')
    monkeypatch.setattr(tsl.race, 'start', lambda go=None: None)
    monkeypatch.setattr(tsl, '_schedule_end_timer', lambda: None)
    monkeypatch.setattr(tsl, 'publish_race_state', lambda: None)
    monkeypatch.setattr(tsl, 'fetch_pending_race', lambda: None)
    monkeypatch.setattr(tsl, 'prev_crossing', [Crossing(CLOCK, 1, 1.0)] * 6)

    tsl._lights_out(tsl._start_generation)()

    assert tsl.prev_crossing == [None] * 6


# --- Lap target for a staged race ---

def _pending(**extra):
    """Minimal /races/pending/ payload: one driver in lane 1."""
    return {
        'race_id': 7,
        'race_number': 3,
        'lane_assignments': [{'lane_number': 1, 'id': 4, 'driver_name': 'Dave', 'lane_enabled': True}],
        **extra,
    }


def test_staged_race_takes_its_lap_target_from_the_payload():
    """Regression: /races/pending/ now carries the session's lap target, so a 5-lap
    session must stage as 5. It used to be a hardcoded 20 at every call site, so a
    staged race showed 20 laps until RaceControl armed it with its own lookup."""
    tsl._load_pending(_pending(target_laps=5))
    assert tsl.race.target_laps == 5


def test_explicit_target_laps_beats_the_payload():
    """An arm/start race_control message naming target_laps is a deliberate instruction
    from a client, so it wins over the payload's default."""
    tsl._load_pending(_pending(target_laps=5), target_laps=12)
    assert tsl.race.target_laps == 12


def test_falls_back_when_the_api_sends_no_lap_target():
    """An API image older than the target_laps field leaves lapdata to guess."""
    tsl._load_pending(_pending())
    assert tsl.race.target_laps == tsl.DEFAULT_TARGET_LAPS
