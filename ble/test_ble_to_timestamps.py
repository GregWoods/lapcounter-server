"""Tests for the BLE Layer 1.

paho and bleak are not installed in the test venv (only api/.venv has pytest, and this
container's deps live in its image), so they are stubbed before import. The module only
uses them for I/O, which sits behind an `if __name__ == '__main__'` guard.
"""
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
    published = []
    monkeypatch.setattr(ble, 'mqtt_client',
                        types.SimpleNamespace(publish=lambda topic, payload: published.append(payload)))
    return published


def packet(car, t1=0, t2=0):
    """An 18-byte Slot notification: seq, car, track1 ms, track2 ms, pitlane (unused)."""
    return bytearray(bytes([0, car]) + struct.pack('<II', t1, t2) + bytes(8))


def crossings(published):
    import json
    return [(json.loads(p)['car'], json.loads(p)['lane']) for p in published]


def stamps(published):
    import json
    return [json.loads(p)['timestamp'] / 1e9 for p in published]


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


# ------------------------------------------------------- device clock anchoring

def test_lap_delta_comes_from_the_device_not_arrival(fresh_state, monkeypatch):
    """The whole point: round-robin reporting jitter must not reach lap times.

    Two crossings exactly 5.000s apart on the powerbase clock, reported with wildly
    different delays. The published stamps must still be 5.000s apart.
    """
    clock = iter([1000.0, 1000.2, 1005.9])   # arrival times: 200ms then 900ms late
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))          # seed
    ble.handle_slot_notification(None, packet(1, t1=10_000))     # crossing at device 10.000s
    ble.handle_slot_notification(None, packet(1, t1=15_000))     # crossing at device 15.000s

    t1, t2 = stamps(fresh_state)
    assert t2 - t1 == pytest.approx(5.0, abs=1e-6)


def test_anchor_converges_on_the_least_delayed_sample(fresh_state, monkeypatch):
    clock = iter([1000.0, 1010.5, 1020.1])   # 500ms late, then only 100ms late
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=10_000))
    assert ble._clock_offset == pytest.approx(1000.5)
    ble.handle_slot_notification(None, packet(1, t1=20_000))
    assert ble._clock_offset == pytest.approx(1000.1)


def test_anchor_never_drifts_upward(fresh_state, monkeypatch):
    """A later, more-delayed sample must not push the anchor back out."""
    clock = iter([1000.0, 1010.1, 1020.9])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=10_000))
    ble.handle_slot_notification(None, packet(1, t1=20_000))
    assert ble._clock_offset == pytest.approx(1000.1)


def test_powerbase_timer_reset_reanchors(fresh_state, monkeypatch):
    """Commands 0/1 zero the powerbase timers; a stale anchor would then date every
    crossing to the distant past."""
    clock = iter([1000.0, 1010.0, 1100.0, 1105.0])
    monkeypatch.setattr(ble.time, 'time', lambda: next(clock))

    ble.handle_slot_notification(None, packet(1, t1=0))
    ble.handle_slot_notification(None, packet(1, t1=10_000))
    assert ble._clock_offset == pytest.approx(1000.0)

    ble.handle_slot_notification(None, packet(1, t1=100))     # timer went backwards
    ble.handle_slot_notification(None, packet(1, t1=5_100))
    published = stamps(fresh_state)
    assert published[-1] == pytest.approx(1105.0, abs=0.01)   # re-anchored to now


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


# --------------------------------------------------------- command payload

def test_command_payload_layout():
    """Bytes 1-6 are a POWER MULTIPLIER, not padding — zeros mean no car moves."""
    payload = bytes([ble.POWER_ON_RACING]) + bytes([ble.FULL_POWER] * 6) + bytes(13)
    assert len(payload) == 20
    assert payload[0] == 3
    assert list(payload[1:7]) == [0x3F] * 6      # full throttle pass-through
    assert payload[1] & 0x80 == 0                # direct-drive override bit clear
    assert list(payload[7:20]) == [0] * 13       # rumble/brake/KERS genuinely unused
