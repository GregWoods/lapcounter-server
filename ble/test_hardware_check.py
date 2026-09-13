"""Tests for hardware_check.py's analysis — the part that decides what the real
powerbase told us, so it has to be right before the one session with the hardware.

paho and bleak are stubbed before import, as in test_ble_to_timestamps.py.
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
    Client=lambda *a, **k: types.SimpleNamespace(publish=lambda *a, **k: None),
    CallbackAPIVersion=types.SimpleNamespace(VERSION2=2),
)
_stub('bleak', BleakClient=object, BleakScanner=object)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import hardware_check as hw  # noqa: E402

S = hw.SlotSample
C = hw.Crossing


# --- crossing detection mirrors ble_to_timestamps ---

def test_first_packet_per_car_only_seeds():
    samples = [S(1.0, 1, 40_000, 0), S(2.0, 1, 45_000, 0)]
    assert hw.find_crossings(samples) == [C(2.0, 1, 1, 45_000)]


def test_zero_and_unchanged_fields_are_not_crossings():
    samples = [S(1.0, 2, 10, 20), S(2.0, 2, 10, 0), S(3.0, 2, 10, 0)]
    assert hw.find_crossings(samples) == []


def test_after_filters_output_but_earlier_samples_still_seed():
    samples = [S(1.0, 1, 100, 0), S(2.0, 1, 200, 0), S(3.0, 1, 300, 0)]
    assert hw.find_crossings(samples, after=2.5) == [C(3.0, 1, 1, 300)]


def test_both_fields_changing_in_one_packet_is_flagged():
    crossings = hw.find_crossings([S(1.0, 3, 0, 0), S(2.0, 3, 500, 510)])
    assert len(crossings) == 2
    assert hw.both_sensors_at_once(crossings) == 1


# --- timing analysis ---

def test_notification_intervals_per_car():
    samples = [S(0.0, 1, 0, 0), S(0.3, 1, 0, 0), S(0.7, 1, 0, 0), S(0.1, 2, 0, 0)]
    result = hw.notification_intervals(samples)
    assert result[1] == {'packets': 3, 'median_gap_ms': 350, 'max_gap_ms': 400}
    assert result[2]['median_gap_ms'] is None


def test_lateness_is_measured_from_the_least_delayed_crossing():
    crossings = [C(100.1, 1, 1, 0), C(105.4, 1, 1, 5_000), C(110.0, 1, 1, 9_800)]
    # offsets 100.1, 100.4, 100.2 -> late by 0, 300, 100 ms
    assert hw.reporting_lateness(crossings) == {'crossings': 3, 'median_ms': 100, 'p95_ms': 300, 'max_ms': 300}
    assert hw.reporting_lateness(crossings[:1]) is None


def test_lap_deltas_separate_device_lap_from_jitter():
    deltas = hw.lap_deltas([C(10.2, 1, 1, 10_000), C(15.5, 1, 1, 15_000), C(16.0, 2, 1, 1)])
    assert deltas == [{'device_s': 5.0, 'wall_s': 5.3, 'jitter_ms': 300}]


def test_double_triggers_same_car_and_sensor_only():
    crossings = [C(1, 1, 1, 1_000), C(1.2, 1, 1, 1_200), C(1.3, 1, 2, 1_300), C(9, 1, 1, 9_000)]
    assert hw.double_triggers(crossings) == [{'car': 1, 'lane': 1, 'gap_ms': 200}]


# --- halt clock semantics (HW-06) ---

@pytest.mark.parametrize('device_elapsed, wall_elapsed, halt, expected', [
    (5.0, 20.0, 15.0, 'paused'),         # device clock skipped the 15s halt
    (5.4, 20.1, 15.0, 'paused'),         # ...allowing for reporting jitter
    (20.0, 20.0, 15.0, 'kept_ticking'),
    (-3.0, 20.0, 15.0, 'reset'),
    (12.0, 20.0, 15.0, 'unclear'),
])
def test_classify_halt_clock(device_elapsed, wall_elapsed, halt, expected):
    assert hw.classify_halt_clock(device_elapsed, wall_elapsed, halt) == expected


def test_classify_halted_crossing():
    before = C(arrival=100.0, car=1, lane=1, device_ms=50_000)     # halt at wall 102
    frozen = C(arrival=110.0, car=2, lane=1, device_ms=52_000)     # device = halt instant
    ticking = C(arrival=110.0, car=2, lane=1, device_ms=60_000)    # device = now
    assert hw.classify_halted_crossing(frozen, before, halt_at=102.0) == 'frozen_at_halt'
    assert hw.classify_halted_crossing(ticking, before, halt_at=102.0) == 'ticking'
    assert hw.classify_halted_crossing(None, before, halt_at=102.0) == 'not_reported'


# --- drift (HW-10) ---

@pytest.mark.parametrize('ppm', [50.0, -80.0, 0.0])
def test_estimate_drift_ppm(ppm):
    start = 10_000.0
    crossings = []
    for i in range(0, 601, 5):
        arrival = start + i
        offset = 1_000.0 + ppm * 1e-6 * i        # the powerbase clock loses/gains ppm
        crossings.append(C(arrival, 1, 1, round((arrival - offset) * 1000)))
    assert hw.estimate_drift_ppm(crossings) == pytest.approx(ppm, abs=5)


def test_drift_needs_a_long_enough_run():
    assert hw.estimate_drift_ppm([C(0, 1, 1, 0), C(100, 1, 1, 100_000)]) is None


# --- helpers ---

def test_values_retained():
    assert hw.values_retained({1: [5, 0], 2: [7, 0]}, {1: [5, 0]}) is True
    assert hw.values_retained({1: [5, 0]}, {1: [0, 0]}) is False
    assert hw.values_retained({1: [5, 0]}, {2: [5, 0]}) is None


@pytest.mark.parametrize('ok, expected', [(True, 'pass'), (False, 'fail'), (None, 'skipped')])
def test_verdict(ok, expected):
    assert hw.verdict(ok) == expected


def test_every_check_id_is_unique_and_documented():
    import pathlib
    ids = [check_id for check_id, _, _ in hw.CHECKS]
    assert len(ids) == len(set(ids))
    doc = (pathlib.Path(__file__).parent / 'HARDWARE_VALIDATION.md').read_text(encoding='utf-8')
    assert all(check_id in doc for check_id in ids)
