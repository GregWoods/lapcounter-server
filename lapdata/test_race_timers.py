"""Tests for lapdata's own timers — start lights, time expiry, the yellow flag — and
the race between a timer callback that has already started and the race_control
command that cancelled it.

paho is not installed in the test venv, so it is stubbed before import. The module only
uses it for I/O, which sits behind an `if __name__ == '__main__'` guard.
"""
import json
import sys
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


PENDING = {
    'race_id': 1, 'race_number': 1,
    'lane_assignments': [{'id': 1, 'driver_name': 'Driver1', 'lane_number': 1}],
}


class FakeTimer:
    """Never runs on its own — a test fires it, so timing is deterministic."""

    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self.cancelled = False
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def is_alive(self):
        return not self.cancelled

    def fire(self):
        self.fn()


@pytest.fixture
def lapdata(monkeypatch):
    """A Running race with one driver, fake timers, and captured race_state messages."""
    timers = []

    def make_timer(interval, fn):
        timer = FakeTimer(interval, fn)
        timers.append(timer)
        return timer

    monkeypatch.setattr(tsl.threading, 'Timer', make_timer)
    published = []
    monkeypatch.setattr(tsl, 'client', types.SimpleNamespace(
        publish=lambda topic, payload: published.append(json.loads(payload))))
    monkeypatch.setattr(tsl, '_post_api', lambda *a, **k: None)
    monkeypatch.setattr(tsl, 'fetch_pending_race', lambda: PENDING)
    monkeypatch.setattr(tsl, 'pending_race_cache', None)
    monkeypatch.setattr(tsl, '_light_timers', [])
    monkeypatch.setattr(tsl, '_end_timer', None)
    monkeypatch.setattr(tsl, '_yellow_timers', [])

    race = tsl.RaceManager()
    race.load_lineup(1, 1, 20, PENDING['lane_assignments'], yellow_grace_seconds=5)
    race.start()
    monkeypatch.setattr(tsl, 'race', race)
    return types.SimpleNamespace(race=race, timers=timers, published=published)


def control(command):
    """As on_message does it: race_control handled under the lock."""
    with tsl._race_lock:
        tsl.handle_race_control({'command': command})


# --- Yellow flag ---

def test_countdown_is_published_by_lapdata_then_power_cuts(lapdata):
    control('yellow')
    assert [t.interval for t in lapdata.timers] == [1, 2, 3, 4, 5]
    for timer in lapdata.timers:
        timer.fire()

    assert [m['yellow_seconds_left'] for m in lapdata.published] == [5, 4, 3, 2, 1, None]
    assert lapdata.published[-1]['state'] == 'Paused'


def test_fractional_grace_still_reaches_one_a_second_before_the_cut(lapdata):
    lapdata.race.yellow_grace_seconds = 5.5
    control('yellow')
    assert [t.interval for t in lapdata.timers] == [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
    assert lapdata.published[0]['yellow_seconds_left'] == 6


def test_resume_now_beats_an_expiry_callback_already_running(lapdata):
    """Timer.cancel() can't stop a callback that has already started. Firing the
    expiry after Resume Now simulates exactly that — power must not be cut."""
    control('yellow')
    expiry = lapdata.timers[-1]
    control('resume')
    published_before = len(lapdata.published)

    expiry.fire()

    assert lapdata.race.state == 'Running'
    assert len(lapdata.published) == published_before


def test_stale_expiry_from_an_earlier_yellow_is_ignored(lapdata):
    """Yellow, resume, yellow again: the first yellow's expiry must not cut the second
    one's grace period short."""
    control('yellow')
    stale_expiry = lapdata.timers[-1]
    control('resume')
    control('yellow')

    stale_expiry.fire()
    assert lapdata.race.state == 'Yellow'

    lapdata.timers[-1].fire()
    assert lapdata.race.state == 'Paused'


@pytest.mark.parametrize('command, state', [('pause', 'Paused'), ('end', 'Finished')])
def test_leaving_yellow_cancels_the_countdown(lapdata, command, state):
    control('yellow')
    yellow_timers = list(lapdata.timers)
    control(command)

    assert all(t.cancelled for t in yellow_timers)
    for timer in yellow_timers:
        timer.fire()
    assert lapdata.race.state == state
    assert lapdata.race.yellow_seconds_left is None


# --- Start lights ---

def test_rearm_ignores_the_previous_arms_lights_out(lapdata):
    """Re-arming while the first countdown's lights-out callback is already running
    must not start the new countdown early."""
    control('arm')
    stale_lights_out = lapdata.timers[-1]
    control('arm')

    stale_lights_out.fire()
    assert lapdata.race.state == 'ArmedForStart'

    lapdata.timers[-1].fire()
    assert lapdata.race.state == 'Running'


def test_end_during_the_countdown_is_not_undone_by_lights_out(lapdata):
    control('arm')
    sequence = list(lapdata.timers)
    control('end')

    for timer in sequence:
        timer.fire()
    assert lapdata.race.state == 'Finished'
    assert lapdata.race.start_lights == 0


# --- Time expiry ---

@pytest.mark.parametrize('command', ['yellow', 'pause'])
def test_time_expiry_ends_a_race_under_a_yellow_flag(lapdata, command):
    """The race clock doesn't stop for a yellow flag, and the expiry timer fires only
    once — skipping a Yellow or Paused race would leave it with no end at all."""
    lapdata.race.race_end_time = time.time() + 60
    tsl._schedule_end_timer()
    end_timer = lapdata.timers[0]
    control(command)
    yellow_timers = lapdata.timers[1:]

    end_timer.fire()

    assert lapdata.race.state == 'Finished'
    assert all(t.cancelled for t in yellow_timers)


def test_stale_end_timer_from_a_previous_race_is_ignored(lapdata):
    lapdata.race.race_end_time = time.time() + 60
    tsl._schedule_end_timer()
    stale = lapdata.timers[-1]
    tsl._schedule_end_timer()      # the next race's start reschedules it

    stale.fire()
    assert lapdata.race.state == 'Running'


# --- Broker (re)connect ---

def test_broker_reconnect_does_not_replace_the_loaded_race(lapdata, monkeypatch):
    """on_connect fires on every reconnect. Reloading the lineup then would swap a
    running race for the next one in the queue."""
    monkeypatch.setattr(tsl, 'fetch_pending_race', lambda: {**PENDING, 'race_id': 2})
    tsl.on_connect(types.SimpleNamespace(subscribe=lambda topic: None), None, None, None, None)

    assert lapdata.race.race_id == 1
    assert lapdata.race.state == 'Running'
    assert lapdata.published[-1]['state'] == 'Running'


def test_first_connect_loads_the_pending_race(lapdata, monkeypatch):
    fresh = tsl.RaceManager()
    monkeypatch.setattr(tsl, 'race', fresh)
    tsl.on_connect(types.SimpleNamespace(subscribe=lambda topic: None), None, None, None, None)

    assert fresh.race_id == 1
    assert fresh.state == 'NotStarted'
