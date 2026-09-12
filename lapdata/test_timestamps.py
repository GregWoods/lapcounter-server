"""Tests for lapdata's handling of Layer 1 crossing timestamps.

paho is not installed in the test venv, so it is stubbed before import. The module only
uses it for I/O, which sits behind an `if __name__ == '__main__'` guard.
"""
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
    Client=lambda *a, **k: types.SimpleNamespace(
        publish=lambda *a, **k: None, on_connect=None, on_message=None,
    ),
    CallbackAPIVersion=types.SimpleNamespace(VERSION2=2),
)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import timestamps_to_lapdata as tsl  # noqa: E402


@pytest.fixture
def now_ns(monkeypatch):
    """Freeze lapdata's clock so 'arrival time' is a known value."""
    fixed = 1_700_000_000_000_000_000
    monkeypatch.setattr(tsl.time, 'time_ns', lambda: fixed)
    return fixed


def test_uses_the_layer1_timestamp(now_ns):
    """The crossing happened when Layer 1 says it did, not when MQTT delivered it."""
    hardware = now_ns - 250_000_000     # reported 250ms late
    assert tsl._crossing_ns({'car': 1, 'timestamp': hardware}) == hardware


def test_falls_back_when_absent(now_ns):
    assert tsl._crossing_ns({'car': 1}) == now_ns


def test_accepts_a_numeric_string(now_ns):
    hardware = now_ns - 1_000_000
    assert tsl._crossing_ns({'car': 1, 'timestamp': str(hardware)}) == hardware


@pytest.mark.parametrize('bad', ['not-a-number', None, [1, 2], {}])
def test_falls_back_on_junk(now_ns, bad):
    assert tsl._crossing_ns({'car': 1, 'timestamp': bad}) == now_ns


@pytest.mark.parametrize('offset_s', [-31, 31, 3600, -86400])
def test_rejects_implausible_stamps(now_ns, offset_s):
    """A Layer 1 with a broken clock must not be able to poison race timing — the Pi
    has no RTC and its clock is set by hand before a meet."""
    stamp = now_ns + offset_s * 1_000_000_000
    assert tsl._crossing_ns({'car': 1, 'timestamp': stamp}) == now_ns


@pytest.mark.parametrize('offset_s', [-29, -1, 0, 29])
def test_accepts_stamps_inside_tolerance(now_ns, offset_s):
    stamp = now_ns + offset_s * 1_000_000_000
    assert tsl._crossing_ns({'car': 1, 'timestamp': stamp}) == stamp


def test_lap_time_comes_from_device_deltas_not_arrival(monkeypatch):
    """End to end through handle_car_timestamp: two crossings 5.000s apart on the
    Layer 1 clock, delivered with very different latency, still measure 5.000s."""
    published = []
    monkeypatch.setattr(tsl, 'client',
                        types.SimpleNamespace(publish=lambda topic, payload: published.append((topic, payload))))
    monkeypatch.setattr(tsl.race, 'on_lap', lambda lane, t: False)
    monkeypatch.setattr(tsl, 'prev_crossing_ns', [0] * 6)

    base = 1_700_000_000_000_000_000
    arrivals = iter([base + 100_000_000, base + 5_900_000_000])   # 100ms then 900ms late
    monkeypatch.setattr(tsl.time, 'time_ns', lambda: next(arrivals))

    tsl.handle_car_timestamp({'car': 1, 'timestamp': base, 'lane': 1})
    tsl.handle_car_timestamp({'car': 1, 'timestamp': base + 5_000_000_000, 'lane': 1})

    import json
    lap_times = [json.loads(p)['lapTime'] for t, p in published if t == 'lap']
    assert lap_times[-1] == pytest.approx(5.0, abs=1e-6)


def test_phantom_filter_uses_device_time(monkeypatch):
    """Two crossings closer together than MINIMUM_LAP_TIME on the device clock are a
    phantom trigger even if network latency spread their arrivals further apart."""
    published = []
    monkeypatch.setattr(tsl, 'client',
                        types.SimpleNamespace(publish=lambda topic, payload: published.append((topic, payload))))
    monkeypatch.setattr(tsl.race, 'on_lap', lambda lane, t: False)
    monkeypatch.setattr(tsl, 'prev_crossing_ns', [0] * 6)
    monkeypatch.setattr(tsl, 'min_lap_time_ns', 4 * 1_000_000_000)

    base = 1_700_000_000_000_000_000
    arrivals = iter([base, base + 10_000_000_000])    # arrivals 10s apart
    monkeypatch.setattr(tsl.time, 'time_ns', lambda: next(arrivals))

    tsl.handle_car_timestamp({'car': 1, 'timestamp': base, 'lane': 1})
    tsl.handle_car_timestamp({'car': 1, 'timestamp': base + 1_000_000_000, 'lane': 1})  # 1s later

    assert len([p for t, p in published if t == 'lap']) == 1
