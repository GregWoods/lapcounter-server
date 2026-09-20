"""Tests for lap_clock: anchoring Layer 1 counters to lapdata's monotonic clock.

Pure module, so no stubbing and no clock patching — every time in here is an explicit
time.monotonic()-style float.
"""
import logging

import pytest

from lap_clock import (
    CLOCK_STEP_CONFIRM_S,
    CLOCK_STEP_THRESHOLD_S,
    ClockAnchors,
    Crossing,
    RaceStart,
    TIMING_ANCHORED,
    TIMING_ARRIVAL,
    TIMING_COUNTER,
    TIMING_FROM_GO,
    interval_s,
)

A = 'ble:aa11bb:1'
B = 'ble:aa11bb:2'


def crossing(clock, counter_ms, arrival):
    return Crossing(clock=clock, counter_ms=counter_ms, arrival=arrival)


# --- The anchor is a running minimum, per clock ---

def test_anchor_takes_the_least_delayed_sample():
    """Every sample is the true offset plus transport delay, and delay is never
    negative, so the smallest sample seen is the best estimate."""
    anchors = ClockAnchors()
    anchors.observe(A, 10_000, 1000.90)   # 900ms late
    anchors.observe(A, 11_000, 1001.05)   # 50ms late — better
    anchors.observe(A, 12_000, 1002.40)   # 400ms late — ignored
    assert anchors.offset(A) == pytest.approx(990.05)


def test_clocks_are_independent():
    anchors = ClockAnchors()
    anchors.observe(A, 10_000, 1000.0)
    anchors.observe(B, 0, 1005.0)
    assert anchors.offset(A) == pytest.approx(990.0)
    assert anchors.offset(B) == pytest.approx(1005.0)


def test_unknown_clock_converts_to_none():
    anchors = ClockAnchors()
    assert anchors.to_local(A, 1234) is None
    assert anchors.to_counter_ms(A, 1000.0) is None


def test_old_clocks_are_retained_up_to_the_limit():
    """A lap spanning a clock change still has to convert its older end, and a yellow
    flag's halt-then-resume burns two clocks at a time."""
    anchors = ClockAnchors(max_clocks=3)
    for n in range(3):
        anchors.observe(f'c{n}', 0, 1000.0 + n)
    assert all(anchors.offset(f'c{n}') is not None for n in range(3))

    anchors.observe('c3', 0, 1003.0)
    assert anchors.offset('c0') is None       # oldest evicted
    assert anchors.offset('c3') is not None


def test_the_clock_in_use_is_not_the_one_evicted():
    """Eviction is by least-recently-observed, not by first-seen: a long-lived clock
    that is still being sampled must outlive a burst of short ones."""
    anchors = ClockAnchors(max_clocks=2)
    anchors.observe(A, 0, 1000.0)
    for n in range(5):
        anchors.observe(f'burst{n}', 0, 1001.0 + n)
        anchors.observe(A, 1000 * (n + 2), 1002.0 + n)
    assert anchors.offset(A) is not None


# --- The divergence guard ---

def test_a_delayed_burst_does_not_move_the_anchor(caplog):
    """A BLE stall delivers a burst of late samples and then prompt ones again.
    Re-anchoring on the burst would stamp every later crossing late."""
    anchors = ClockAnchors()
    anchors.observe(A, 0, 1000.0)
    late = CLOCK_STEP_THRESHOLD_S + 2
    # Late for less than the confirmation period...
    for t in range(0, int(CLOCK_STEP_CONFIRM_S) - 1):
        anchors.observe(A, t * 1000, 1000.0 + t + late)
    # ...then prompt again.
    anchors.observe(A, 10_000, 1010.0)
    assert anchors.offset(A) == pytest.approx(1000.0)


def test_a_sustained_divergence_re_anchors_and_logs_an_error(caplog):
    """Nothing legitimate does this: lapdata's clock is monotonic, so a counter that
    keeps falling behind is a Layer 1 that broke it without starting a new clock."""
    anchors = ClockAnchors()
    anchors.observe(A, 0, 1000.0)
    drift = CLOCK_STEP_THRESHOLD_S + 1
    with caplog.at_level(logging.ERROR):
        for t in range(0, int(CLOCK_STEP_CONFIRM_S) + 1):
            anchors.observe(A, t * 1000, 1000.0 + t + drift)
    assert anchors.offset(A) == pytest.approx(1000.0 + drift)
    assert A in caplog.text


def test_drift_under_the_threshold_is_never_corrected():
    anchors = ClockAnchors()
    anchors.observe(A, 0, 1000.0)
    drift = CLOCK_STEP_THRESHOLD_S - 0.5
    for t in range(0, int(CLOCK_STEP_CONFIRM_S) + 5):
        anchors.observe(A, t * 1000, 1000.0 + t + drift)
    assert anchors.offset(A) == pytest.approx(1000.0)


# --- Intervals ---

def test_same_clock_intervals_are_exact_however_jittery_the_arrivals():
    """The whole point: two crossings 5.000s apart on Layer 1's counter measure
    5.000s even when MQTT delivered them 100ms and 900ms late."""
    anchors = ClockAnchors()
    a = crossing(A, 10_000, 1010.1)
    b = crossing(A, 15_000, 1015.9)
    seconds, timing = interval_s(a, b, anchors)
    assert seconds == pytest.approx(5.0)
    assert timing == TIMING_COUNTER


def test_same_clock_interval_needs_no_anchor_at_all():
    a = crossing(A, 10_000, 1010.0)
    b = crossing(A, 14_500, 1014.5)
    assert interval_s(a, b, ClockAnchors())[0] == pytest.approx(4.5)


def test_cross_clock_interval_uses_the_anchors():
    """A lap spanning a yellow-flag halt: the counter stopped, so Layer 1 started a new
    clock and the lap has to be measured through lapdata's clock instead."""
    anchors = ClockAnchors()
    anchors.observe(A, 10_000, 1010.0)      # offset 1000.0
    anchors.observe(B, 0, 1013.0)           # offset 1013.0 — 3s of halt
    a = crossing(A, 10_000, 1010.0)
    b = crossing(B, 2_000, 1015.0)
    seconds, timing = interval_s(a, b, anchors)
    assert seconds == pytest.approx(5.0)    # 3s halted + 2s running
    assert timing == TIMING_ANCHORED


def test_cross_clock_interval_falls_back_to_arrival_without_an_anchor():
    anchors = ClockAnchors()
    anchors.observe(B, 0, 1013.0)
    a = crossing('evicted', 10_000, 1010.0)
    b = crossing(B, 2_000, 1015.0)
    seconds, timing = interval_s(a, b, anchors)
    assert seconds == pytest.approx(5.0)
    assert timing == TIMING_ARRIVAL


# --- Lights-out correlation ---

def test_go_is_frozen_on_first_use_so_every_car_shares_one_error():
    """Two cars' lap-1 errors must be identical even when the anchor improves between
    their crossings — otherwise a better anchor for the second car changes their
    relative lap 1 times, and with them the order."""
    anchors = ClockAnchors()
    anchors.observe(A, 0, 1000.5)           # 500ms late: offset 1000.5
    start = RaceStart(local=1000.0)

    lap1_car1, _ = start.since_go(crossing(A, 5_000, 1005.6), anchors)

    anchors.observe(A, 6_000, 1006.0)       # a much better sample: offset 1000.0
    lap1_car2, _ = start.since_go(crossing(A, 5_000, 1005.6), anchors)

    assert lap1_car1 == pytest.approx(lap1_car2)


def test_a_counter_zero_sample_anchors_to_within_its_lateness():
    """Plan B's fallback shape: a `counter_ms: 0` sample published once the write that
    zeroed the clock is acknowledged.

    Note the direction: a late sample overestimates the offset, which puts go *earlier*
    on the counter, so lap 1 reads LONG by the sample's lateness. That is the safe way
    round — anchor error can never fabricate a too-fast lap, only a too-slow one."""
    anchors = ClockAnchors()
    anchors.observe(A, 0, 1000.02)          # 20ms late
    start = RaceStart(local=1000.0)
    seconds, timing = start.since_go(crossing(A, 5_000, 1005.1), anchors)
    assert timing == TIMING_FROM_GO
    assert seconds == pytest.approx(5.02, abs=1e-6)


def test_lap_one_from_go_is_exact_with_a_perfect_anchor():
    anchors = ClockAnchors()
    anchors.observe(A, 10_000, 1010.0)
    start = RaceStart(local=1000.0)
    seconds, timing = start.since_go(crossing(A, 4_500, 1004.7), anchors)
    assert seconds == pytest.approx(4.5)
    assert timing == TIMING_FROM_GO


def test_lap_one_falls_back_to_arrival_without_an_anchor():
    start = RaceStart(local=1000.0)
    seconds, timing = start.since_go(crossing(A, 4_500, 1004.7), ClockAnchors())
    assert seconds == pytest.approx(4.7)
    assert timing == TIMING_ARRIVAL


def test_each_clock_gets_its_own_frozen_go():
    """Both GPIO lane containers share one clock, but a mid-race Layer 1 change (or a
    halt) means a car's first crossing can land on a clock go was never converted to."""
    anchors = ClockAnchors()
    anchors.observe(A, 10_000, 1010.0)      # offset 1000.0
    anchors.observe(B, 0, 1002.0)           # offset 1002.0
    start = RaceStart(local=1000.0)
    assert start.counter_for(A, anchors) == pytest.approx(0.0)
    assert start.counter_for(B, anchors) == pytest.approx(-2000.0)
