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


def ticks(seconds):
    """Device seconds as raw powerbase ticks (10ms on real hardware, see DEVICE_TICK_S)."""
    return round(seconds / hw.ble.DEVICE_TICK_S)


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
    crossings = [C(100.1, 1, 1, 0), C(105.4, 1, 1, ticks(5.0)), C(110.0, 1, 1, ticks(9.8))]
    # offsets 100.1, 100.4, 100.2 -> late by 0, 300, 100 ms
    assert hw.reporting_lateness(crossings) == {'crossings': 3, 'median_ms': 100, 'p95_ms': 300, 'max_ms': 300}
    assert hw.reporting_lateness(crossings[:1]) is None


def test_lap_deltas_separate_device_lap_from_jitter():
    deltas = hw.lap_deltas([C(10.2, 1, 1, ticks(10.0)), C(15.5, 1, 1, ticks(15.0)), C(16.0, 2, 1, 1)])
    assert deltas == [{'device_s': 5.0, 'wall_s': 5.3, 'jitter_ms': 300}]


def test_real_powerbase_counts_10ms_ticks():
    """From the first hardware run (2026-09-18): a lap that took 54.08s by our clock came
    back as 5296. Read as the protocol doc's milliseconds that is a 5.3s lap, and every
    lap fell under MINIMUM_LAP_TIME. As 10ms ticks it is 52.96s, off by one rotation."""
    (delta,) = hw.lap_deltas([C(1_000.0, 5, 1, 0), C(1_054.075, 5, 1, 5_296)])
    assert delta['device_s'] == pytest.approx(52.96)
    assert abs(delta['jitter_ms']) < 1_800        # within one ~1.8s Slot rotation


def test_double_triggers_same_car_and_sensor_only():
    crossings = [C(1, 1, 1, ticks(1.0)), C(1.2, 1, 1, ticks(1.2)), C(1.3, 1, 2, ticks(1.3)),
                 C(9, 1, 1, ticks(9.0))]
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
    before = C(arrival=100.0, car=1, lane=1, device_ticks=ticks(50.0))     # halt at wall 102
    frozen = C(arrival=110.0, car=2, lane=1, device_ticks=ticks(52.0))     # device = halt instant
    ticking = C(arrival=110.0, car=2, lane=1, device_ticks=ticks(60.0))    # device = now
    assert hw.classify_halted_crossing(frozen, before, halt_at=102.0) == 'frozen_at_halt'
    assert hw.classify_halted_crossing(ticking, before, halt_at=102.0) == 'ticking'
    assert hw.classify_halted_crossing(None, before, halt_at=102.0) == 'not_reported'


# --- drift (HW-10) ---

# 10ms ticks resolve ~20ppm over this 10-minute run, so test drifts well above that.
@pytest.mark.parametrize('ppm', [500.0, -800.0, 0.0])
def test_estimate_drift_ppm(ppm):
    start = 10_000.0
    crossings = []
    for i in range(0, 601, 5):
        arrival = start + i
        offset = 1_000.0 + ppm * 1e-6 * i        # the powerbase clock loses/gains ppm
        crossings.append(C(arrival, 1, 1, ticks(arrival - offset)))
    assert hw.estimate_drift_ppm(crossings) == pytest.approx(ppm, abs=25)


def test_drift_needs_a_long_enough_run():
    assert hw.estimate_drift_ppm([C(0, 1, 1, 0), C(100, 1, 1, ticks(100.0))]) is None


# --- command 1 then 3 (HW-11) ---

@pytest.mark.parametrize('device_s, since_ready, since_go, expected', [
    (13.2, 13.5, 3.5, 'ticked_from_ready'),   # zeroed at 1, ticking through the 10s hold
    (3.1, 13.5, 3.5, 'started_at_go'),        # held at zero until 3
    (412.0, 13.5, 3.5, 'not_reset'),
    (8.0, 13.5, 3.5, 'unclear'),
])
def test_classify_ready_clock(device_s, since_ready, since_go, expected):
    assert hw.classify_ready_clock(device_s, since_ready, since_go) == expected


@pytest.mark.parametrize('device_elapsed, wall_elapsed, expected', [
    (5.0, 5.3, 'unaffected'),
    (-40.0, 5.3, 'reset'),
    (1.0, 5.3, 'unclear'),
])
def test_classify_resend(device_elapsed, wall_elapsed, expected):
    assert hw.classify_resend(device_elapsed, wall_elapsed) == expected


# --- throttleTimestamp (HW-12) ---

T = hw.ThrottleSample


def live_stream(start=100.0, n=50, gap=0.05, offset=90.0, late=lambda i: 0.01 * (i % 3)):
    """Samples reading a clock that is `offset` behind ours, reported a little late."""
    return [T(start + i * gap + late(i), ticks(start + i * gap - offset), (0,) * 6)
            for i in range(n)]


def test_throttle_stream_live_clock():
    stats = hw.throttle_stream(live_stream(late=lambda i: 0))
    assert stats['median_gap_ms'] == 50 and stats['max_gap_ms'] == 50
    assert stats['advancing_fraction'] == 1.0
    assert stats['device_to_wall_rate'] == pytest.approx(1.0, abs=0.001)
    assert hw.is_live(stats) is True


def test_throttle_stream_lateness_from_the_least_delayed_notification():
    stats = hw.throttle_stream(live_stream())      # 0, 10 or 20ms late
    assert stats['lateness'] == {'notifications': 50, 'median_ms': 10, 'p95_ms': 20, 'max_ms': 20}
    assert hw.is_live(stats) is True


def test_throttle_stream_stale_at_rest():
    """A timestamp that only updates when a throttle moves is no heartbeat."""
    stale = [T(100.0 + i * 0.05, 10_000, (0,) * 6) for i in range(50)]
    stats = hw.throttle_stream(stale)
    assert stats['advancing_fraction'] == 0.0
    assert hw.is_live(stats) is False
    assert hw.is_live(None) is None


def test_max_throttle_per_car_masks_button_bits():
    """0x40 is the brake button and 0x80 lane change: neither is throttle."""
    samples = [T(1.0, 0, (2, 0x45, 0, 0, 0, 0)), T(1.1, 0, (1, 0x80, 0, 0, 0, 3))]
    assert hw.max_throttle_per_car(samples) == [2, 5, 0, 0, 0, 3]
    assert hw.max_throttle_per_car([]) is None


def test_compare_clock_offsets_same_clock():
    throttle = live_stream()                                            # offset 90.000
    crossings = [C(101.3, 1, 1, ticks(11.0)), C(103.45, 1, 1, ticks(13.2))]      # offsets 90.3, 90.25
    result = hw.compare_clock_offsets(throttle, crossings)
    assert result['slot_minus_throttle_ms'] == 250
    assert result['agree'] is True


def test_compare_clock_offsets_different_clock():
    crossings = [C(101.3, 1, 1, ticks(1.0)), C(103.4, 1, 1, ticks(3.05))]         # offset ~100.3
    assert hw.compare_clock_offsets(live_stream(), crossings)['agree'] is False
    assert hw.compare_clock_offsets([], crossings) is None


def test_classify_clock_window():
    ticking = live_stream(start=100.0, n=100, gap=0.1)                   # 10s of samples
    assert hw.classify_clock_window(ticking, 100.0, 110.0)['behaviour'] == 'ticking'
    halted = [T(100.0 + i * 0.1, ticks(5.0), (0,) * 6) for i in range(100)]
    assert hw.classify_clock_window(halted, 100.0, 110.0)['behaviour'] == 'halted'
    backwards = [T(100.0, ticks(50.0), (0,) * 6), T(105.0, ticks(2.0), (0,) * 6)]
    assert hw.classify_clock_window(backwards, 100.0, 110.0)['behaviour'] == 'went_backwards'
    assert hw.classify_clock_window(ticking, 100.0, 100.5)['behaviour'] == 'too_short'
    assert hw.classify_clock_window(ticking, 500.0, 600.0)['behaviour'] == 'no_data'


def test_clock_zeroed():
    before = T(99.9, ticks(400.0), (0,) * 6)
    assert hw.clock_zeroed(before, T(101.0, ticks(0.9), (0,) * 6), write_at=100.0) is True
    assert hw.clock_zeroed(before, T(101.0, ticks(401.1), (0,) * 6), write_at=100.0) is False
    assert hw.clock_zeroed(before, None, write_at=100.0) is None


@pytest.mark.parametrize('evidence, expected', [
    ({'offsets_agree': True, 'halt_matches_slot': True, 'zeroing_matches_slot': True}, 'same_clock'),
    ({'offsets_agree': True, 'halt_matches_slot': None, 'zeroing_matches_slot': None}, 'same_clock'),
    ({'offsets_agree': True, 'halt_matches_slot': False, 'zeroing_matches_slot': True}, 'different_clock'),
    ({'offsets_agree': False, 'halt_matches_slot': None, 'zeroing_matches_slot': None}, 'different_clock'),
    ({'offsets_agree': None, 'halt_matches_slot': True, 'zeroing_matches_slot': None}, 'unclear'),
])
def test_conclude_same_clock(evidence, expected):
    assert hw.conclude_same_clock(evidence) == expected


def test_samples_between_and_neighbours():
    samples = [T(float(t), t, ()) for t in (1, 2, 3, 4)]
    assert [s.arrival for s in hw.samples_between(samples, 2, 3)] == [2.0, 3.0]
    assert hw.last_before(samples, 3).arrival == 2.0
    assert hw.first_after(samples, 3).arrival == 4.0
    assert hw.last_before(samples, 1) is None and hw.first_after(samples, 4) is None


# --- powerbase buttons (HW-13) ---

def test_bytes_new_in_window_ignores_noisy_positions():
    """Sequence counters and live timestamps vary anyway; only a byte that was steady and
    then changed while pressing counts."""
    baseline = [('throttle', bytes([0, 0, 0, 1])), ('throttle', bytes([1, 0, 0, 1])), ('track', bytes([0, 0]))]
    window = [('throttle', bytes([2, 0x40, 0, 1])), ('throttle', bytes([3, 0, 0, 5])), ('track', bytes([0, 0]))]
    assert hw.bytes_new_in_window(baseline, window) == {'throttle': {1: [0x40], 3: [5]}}
    assert hw.bytes_new_in_window(baseline, baseline) == {}


# --- Slot polling (HW-14) ---

def test_compare_poll_to_notify_measures_how_much_sooner_polling_saw_a_crossing():
    # Polling cycles car IDs and sees car 5's crossing (device tick 900) at 10.1s;
    # the round-robin notification only brings it at 11.5s.
    polled = [S(9.0, 5, 800, 0), S(9.05, 1, 0, 0), S(10.1, 5, 900, 0), S(10.15, 1, 0, 0)]
    notified = [S(9.7, 5, 800, 0), S(11.5, 5, 900, 0)]
    result = hw.compare_poll_to_notify(polled, notified)
    assert result['crossings'] == {'seen_by_both': 1, 'only_polling': 0, 'only_notify': 0}
    assert result['polling_earlier_ms'] == {'median': 1400, 'min': 1400, 'max': 1400}
    assert result['car_id_change_fraction'] == 1.0
    assert result['cars_seen_by_polling'] == [1, 5]


def test_compare_poll_to_notify_with_no_reads():
    result = hw.compare_poll_to_notify([], [S(1.0, 5, 1, 0)])
    assert result['reads'] == 0 and result['polling_earlier_ms'] is None


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
