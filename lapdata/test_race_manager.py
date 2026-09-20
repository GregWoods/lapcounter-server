import pytest
from lap_clock import ClockAnchors, Crossing, TIMING_ANCHORED, TIMING_COUNTER, TIMING_FROM_GO
from race_manager import RaceManager

# Lights-out on lapdata's monotonic clock, and the Layer 1 clock the cars run on. The
# anchor is set up so counter 0 lands exactly on GO, which makes at(t) below read as
# "t seconds after lights-out" on both clocks at once.
GO = 1000.0
CLOCK = 'test:1'


def at(seconds_after_go, clock=CLOCK, late=0.0):
    """A crossing `seconds_after_go` after lights-out, reported `late` seconds after it
    happened. The lateness is exactly what must NOT end up in a lap time."""
    return Crossing(clock=clock,
                    counter_ms=round(seconds_after_go * 1000),
                    arrival=GO + seconds_after_go + late)


def make_lineup(n=3):
    """lane_assignments for lanes 1..n, driver_id = lane, named DriverN."""
    return [
        {'id': lane, 'driver_name': f'Driver{lane}', 'lane_number': lane}
        for lane in range(1, n + 1)
    ]


def new_race(target_laps=3, count_first_crossing=False, n_drivers=3, session_type='Points',
             race_duration_seconds=None, session_drivers=None, anchors=None):
    # A perfect anchor by default: counter 0 exactly at GO, so at(t) reads as t seconds
    # of lap time. Tests that care about anchor error build their own and pass it in.
    if anchors is None:
        anchors = ClockAnchors()
        anchors.observe(CLOCK, 0, GO)
    race = RaceManager(anchors)
    race.load_lineup(
        race_id=1, race_number=1, target_laps=target_laps,
        lane_assignments=make_lineup(n_drivers),
        count_first_crossing=count_first_crossing,
        session_type=session_type,
        race_duration_seconds=race_duration_seconds,
        session_drivers=session_drivers,
    )
    race.start(GO)
    return race


# --- No race loaded ---

def test_no_race_loaded_publishes_null_identities():
    """Regression: race_id and race_number must be None, not 0, before a lineup is loaded.

    lapdata publishes race_state whenever asked (the `status` command), including when it
    started against an empty queue and has no race. A 0 there is a race that doesn't exist,
    and every consumer has to know to treat it as falsy. RaceControl used `??`, which only
    falls back on null, so a 0 went through and the title read "No race of 7"."""
    race = RaceManager()
    state = race.to_dict()
    assert state['race_id'] is None
    assert state['race_number'] is None


# --- Discarded first crossing (CLAUDE.md-documented footgun) ---

def test_discarded_first_crossing_not_counted_as_lap():
    race = new_race(count_first_crossing=False)
    race.on_lap(1, at(0.5))
    driver = race.drivers[1]
    assert driver.laps_completed == 0
    assert driver.crossings == 1


def test_discarded_first_crossing_still_sets_last_crossing():
    """Regression test: last_crossing must be set even when the first crossing is
    discarded, or race_time() silently returns 0.0 and position sort falls back to
    lane-number order instead of crossing order."""
    race = new_race(count_first_crossing=False)
    crossing = at(0.5)
    race.on_lap(1, crossing)
    driver = race.drivers[1]
    assert driver.last_crossing == crossing
    assert race.race_time(driver) == pytest.approx(0.5)


def test_count_first_crossing_true_counts_lap_one():
    race = new_race(count_first_crossing=True)
    race.on_lap(1, at(5.0))
    driver = race.drivers[1]
    assert driver.laps_completed == 1
    assert driver.last_lap_time == pytest.approx(5.0)


# --- Lap timing ---

def test_lap_one_timed_from_race_start():
    race = new_race(count_first_crossing=True)
    race.on_lap(1, at(4.5))
    assert race.drivers[1].last_lap_time == pytest.approx(4.5)
    assert race.drivers[1].last_lap_timing == TIMING_FROM_GO


def test_subsequent_laps_timed_from_previous_crossing():
    race = new_race(count_first_crossing=True)
    race.on_lap(1, at(4.5))
    race.on_lap(1, at(9.0))
    driver = race.drivers[1]
    assert driver.laps_completed == 2
    assert driver.last_lap_time == pytest.approx(4.5)
    assert driver.lap_times == [pytest.approx(4.5), pytest.approx(4.5)]


def test_discarded_crossing_then_first_real_lap_still_timed_from_lights_out():
    """⚠️ Lap 1 is timed from lights-out in EVERY race, whatever the start grid (Greg,
    2026-09-20). The discard only affects which crossing *ends* lap 1, never the base it
    is timed from: a driver's race begins when the lights go out, not when they happen to
    reach the line. So here lap 1 is lights-out -> the SECOND crossing, part-lap
    included."""
    race = new_race(count_first_crossing=False)
    race.on_lap(1, at(0.5))   # discarded start-line crossing
    race.on_lap(1, at(5.0))   # lap 1: real
    driver = race.drivers[1]
    assert driver.laps_completed == 1
    assert driver.last_lap_time == pytest.approx(5.0)
    assert driver.last_lap_timing == TIMING_FROM_GO


def test_lap_times_ignore_reporting_lateness():
    """The point of the whole counter contract: BLE's Slot characteristic is round-robin
    across 6 cars, so a crossing can be reported up to a rotation (~1.8s on the measured
    hardware) after it happened. None of that jitter may reach a lap time."""
    race = new_race(count_first_crossing=True)
    race.on_lap(1, at(4.5, late=1.7))
    race.on_lap(1, at(9.0, late=0.05))
    driver = race.drivers[1]
    assert driver.lap_times == [pytest.approx(4.5), pytest.approx(4.5)]
    assert driver.last_lap_timing == TIMING_COUNTER


def test_lap_two_onwards_needs_no_anchor_at_all():
    """Lap 2+ is a plain counter subtraction, so a deliberately wrong anchor can't
    touch it. Only lap 1 crosses from Layer 1's clock onto ours."""
    anchors = ClockAnchors()
    anchors.observe(CLOCK, 0, GO + 30)        # 30s out
    race = new_race(count_first_crossing=True, anchors=anchors)
    race.on_lap(1, at(5.0))
    race.on_lap(1, at(9.4))
    assert race.drivers[1].lap_times[-1] == pytest.approx(4.4)


@pytest.mark.parametrize('count_first_crossing', [True, False])
def test_lap_one_always_depends_on_the_anchor(count_first_crossing):
    """Whatever the start grid, lap 1 is measured from lights-out, so it is the one lap
    in every race that crosses from Layer 1's clock onto ours. A deliberately wrong
    anchor shows up in it — which is exactly why layer1_clock exists, and why it matters
    in every race rather than only when the first crossing counts."""
    anchors = ClockAnchors()
    anchors.observe(CLOCK, 0, GO + 30)        # 30s out
    race = new_race(count_first_crossing=count_first_crossing, anchors=anchors)
    if not count_first_crossing:
        race.on_lap(1, at(0.4))               # discarded start-line crossing
    race.on_lap(1, at(5.6))                   # lap 1 either way

    assert race.drivers[1].last_lap_timing == TIMING_FROM_GO
    assert race.drivers[1].last_lap_time == pytest.approx(35.6)


def test_lap_one_error_is_identical_for_every_car():
    """Go is converted onto the counter once per race and frozen, so an anchor that
    improves between two cars' first crossings cannot change their relative lap 1s —
    it can only shift both by the same amount."""
    anchors = ClockAnchors()
    anchors.observe(CLOCK, 0, GO + 0.4)       # 400ms-late first sample
    race = new_race(count_first_crossing=True, n_drivers=2, anchors=anchors)

    race.on_lap(1, at(5.0))
    anchors.observe(CLOCK, 6_000, GO + 6.0)   # a perfect sample lands between the two
    race.on_lap(2, at(6.0))

    lap1, lap2 = race.drivers[1].last_lap_time, race.drivers[2].last_lap_time
    assert lap2 - lap1 == pytest.approx(1.0)  # the true 1.0s gap, undistorted
    assert lap1 == pytest.approx(5.4)         # both carry the same +0.4s anchor error


def test_a_lap_spanning_a_clock_change_is_anchored_and_includes_the_halt():
    """A yellow flag halts the powerbase's counter, so Layer 1 starts a new clock. The
    lap either side of it can't be a counter subtraction, and it keeps the halt in —
    which matches a stopwatch, and makes the lap far too slow to be a fastest lap."""
    anchors = ClockAnchors()
    anchors.observe(CLOCK, 0, GO)
    race = new_race(count_first_crossing=True, anchors=anchors)
    race.on_lap(1, at(5.0))

    after_halt = 'test:2'
    anchors.observe(after_halt, 0, GO + 13.0)     # 8s halted from the 5.0s crossing
    race.on_lap(1, Crossing(clock=after_halt, counter_ms=2_000, arrival=GO + 15.0))

    driver = race.drivers[1]
    # 8s from the last crossing to the new clock's zero (racing, then halted), then 2s
    # of racing on the new clock.
    assert driver.last_lap_time == pytest.approx(10.0)
    assert driver.last_lap_timing == TIMING_ANCHORED


def test_positions_follow_the_counters_even_when_arrivals_are_out_of_order():
    """Two cars crossing 100ms apart must not be reordered by which car's round-robin
    Slot packet happened to arrive first."""
    race = new_race(target_laps=5, count_first_crossing=True, n_drivers=2)
    race.on_lap(1, at(5.10, late=0.05))    # lane 1 crossed second, reported first
    race.on_lap(2, at(5.00, late=0.30))

    by_lane = {d['lane']: d for d in race.to_dict()['drivers']}
    assert by_lane[2]['position'] == 1
    assert by_lane[1]['position'] == 2


# --- Fastest lap tracking ---

def test_best_lap_and_race_fastest_lap_tracked():
    race = new_race(count_first_crossing=True, n_drivers=2)
    race.on_lap(1, at(5.0))
    race.on_lap(2, at(4.0))
    race.on_lap(1, at(5.0 + 4.5))
    assert race.drivers[1].best_lap_time == pytest.approx(4.5)
    assert race.drivers[2].best_lap_time == pytest.approx(4.0)
    assert race.race_fastest_lap == pytest.approx(4.0)


def test_a_crossing_with_no_recorded_lights_out_does_not_fabricate_a_lap():
    """resume() sets Running without a start(), so a 'resume' sent to a freshly started
    lapdata gets here. A fabricated 0.0s lap would win fastest lap outright and stand for
    the whole session."""
    race = RaceManager(ClockAnchors())
    race.load_lineup(1, 1, 5, make_lineup(1), count_first_crossing=True)
    race.resume()
    assert race.state == 'Running' and race.race_start is None

    assert race.on_lap(1, at(5.0)) is True
    assert race.drivers[1].laps_completed == 0
    assert race.race_fastest_lap == 999.999

    race.on_lap(1, at(9.5))                      # now there is something to measure from
    assert race.drivers[1].last_lap_time == pytest.approx(4.5)


# --- Ignored crossings ---

def test_on_lap_ignored_when_not_running():
    race = new_race(count_first_crossing=True)
    race.pause()
    updated = race.on_lap(1, at(5.0))
    assert updated is False
    assert race.drivers[1].laps_completed == 0


def test_on_lap_ignored_for_unknown_lane():
    race = new_race(count_first_crossing=True, n_drivers=2)
    updated = race.on_lap(5, at(5.0))
    assert updated is False


def test_on_lap_ignored_once_driver_finished():
    race = new_race(target_laps=1, count_first_crossing=True, n_drivers=2)
    race.on_lap(1, at(5.0))
    assert race.drivers[1].finished is True
    updated = race.on_lap(1, at(10.0))
    assert updated is False
    assert race.drivers[1].laps_completed == 1


# --- Yellow flag (grace period, then power cut) ---

@pytest.mark.parametrize('grace, expected', [(8.0, 8), (7.5, 8), (1, 1)])
def test_yellow_sets_state_and_seconds_left(grace, expected):
    """A whole-second countdown lapdata publishes, not a deadline a display has to
    compare against its own (possibly wrong) clock."""
    race = new_race(count_first_crossing=True)
    race.yellow_grace_seconds = grace
    race.yellow()
    assert race.state == 'Yellow'
    assert race.yellow_seconds_left == expected
    assert race.to_dict()['yellow_seconds_left'] == expected


def test_laps_are_counted_during_yellow():
    """⚠️ Regression (Greg, 2026-09-20): Yellow used to be treated like Paused, so every
    crossing in the grace window was silently thrown away — while the powerbase was still
    at full power and the cars were still racing. The grace period exists so drivers can
    finish the corner and get clear; those are real laps."""
    race = new_race(count_first_crossing=True)
    race.yellow()
    updated = race.on_lap(1, at(5.0))
    assert updated is True
    assert race.drivers[1].laps_completed == 1
    assert race.drivers[1].last_lap_time == pytest.approx(5.0)


def test_laps_not_counted_once_paused():
    """The power cut is what stops the counting, not the yellow flag."""
    race = new_race(count_first_crossing=True)
    race.yellow()
    race.pause()
    updated = race.on_lap(1, at(5.0))
    assert updated is False
    assert race.drivers[1].laps_completed == 0


def test_a_race_can_finish_during_the_yellow_grace_period():
    """A driver taking the chequered flag before the power cut ends the race there — and
    the countdown must not still be running in the published state."""
    race = new_race(target_laps=1, count_first_crossing=True, n_drivers=1)
    race.yellow()
    race.on_lap(1, at(5.0))
    assert race.drivers[1].finished is True
    assert race.state == 'Finished'
    assert race.yellow_seconds_left is None
    assert race.to_dict()['yellow_seconds_left'] is None


def test_pause_from_yellow_clears_countdown():
    """The grace-expiry timer calls pause() directly (see timestamps_to_lapdata.py's
    _yellow_expiry) — it must land on a clean Paused state, not a stale countdown."""
    race = new_race(count_first_crossing=True)
    race.yellow()
    race.pause()
    assert race.state == 'Paused'
    assert race.yellow_seconds_left is None


def test_resume_from_yellow_clears_countdown():
    """'Resume Now' during the grace window goes straight back to Running, cancelling
    the countdown (the caller is responsible for cancelling the actual timer)."""
    race = new_race(count_first_crossing=True)
    race.yellow()
    race.resume()
    assert race.state == 'Running'
    assert race.yellow_seconds_left is None


# --- Chequered flag / race end ---

def test_other_drivers_finish_on_their_next_crossing_after_winner():
    """A driver who has already started (crossed at least once) keeps the race
    open until their next crossing, even after someone else hits the target —
    this is what gives trailing-but-running drivers one more lap."""
    race = new_race(target_laps=2, count_first_crossing=True, n_drivers=2)
    race.on_lap(2, at(5.0))    # driver 2 has started (lap 1)
    race.on_lap(1, at(5.0))
    race.on_lap(1, at(10.0))   # driver 1 wins, finishes
    assert race.drivers[1].finished is True
    assert race.drivers[2].finished is False
    assert race.state == 'Running'                # driver 2 has started, not yet finished

    race.on_lap(2, at(9.0))     # driver 2's next crossing
    assert race.drivers[2].finished is True
    assert race.drivers[2].laps_completed == 2
    assert race.state == 'Finished'


def test_race_ends_when_all_started_drivers_finished():
    race = new_race(target_laps=2, count_first_crossing=True, n_drivers=2)
    race.on_lap(2, at(5.0))    # driver 2 has started
    race.on_lap(1, at(5.0))
    race.on_lap(1, at(10.0))   # driver 1 finishes
    assert race.state == 'Running'                # driver 2 started, hasn't finished yet
    race.on_lap(2, at(9.0))
    assert race.state == 'Finished'


def test_race_ends_when_remaining_drivers_never_started():
    """A driver who never crosses the line at all doesn't block race end."""
    race = new_race(target_laps=1, count_first_crossing=True, n_drivers=2)
    race.on_lap(1, at(5.0))
    assert race.drivers[1].finished is True
    assert race.state == 'Finished'  # driver 2 never started, doesn't block


# --- to_dict / position sorting ---

def test_to_dict_sorted_by_laps_then_started_then_race_time_but_output_sorted_by_lane():
    race = new_race(target_laps=5, count_first_crossing=True, n_drivers=3)
    race.on_lap(1, at(5.0))   # lane 1: 1 lap
    race.on_lap(2, at(5.0))   # lane 2: 1 lap
    race.on_lap(2, at(9.0))   # lane 2: 2 laps (ahead)
    # lane 3 never crosses

    state = race.to_dict()
    by_lane = {d['lane']: d for d in state['drivers']}
    assert by_lane[2]['position'] == 1
    assert by_lane[1]['position'] == 2
    assert by_lane[3]['position'] == 3
    # driver_list itself is sorted back to lane order for React
    assert [d['lane'] for d in state['drivers']] == [1, 2, 3]


def test_to_dict_standard_fields():
    race = new_race(target_laps=5, count_first_crossing=True, n_drivers=1)
    race.on_lap(1, at(4.321))
    state = race.to_dict()
    assert state['race_id'] == 1
    assert state['state'] == 'Running'
    d = state['drivers'][0]
    assert d['laps_completed'] == 1
    assert d['laps_remaining'] == 4
    assert d['last_lap'] == pytest.approx(4.321)
    assert d['best_lap'] == pytest.approx(4.321)
    assert d['has_started'] is True
    assert d['finished'] is False
    assert d['is_race_fastest_lap'] is True


def test_suspended_flag_set_when_far_behind_leader():
    race = new_race(target_laps=10, count_first_crossing=True, n_drivers=2)
    race.on_lap(1, at(5.0))
    race.on_lap(2, at(5.0))
    race.on_lap(2, at(20.0))   # lane 2 pulls well ahead in race_time

    state = race.to_dict()
    by_lane = {d['lane']: d for d in state['drivers']}
    assert by_lane[1]['suspended'] is True
    assert by_lane[2]['suspended'] is False


def test_driver_never_crossed_not_suspended():
    race = new_race(target_laps=10, count_first_crossing=True, n_drivers=2)
    race.on_lap(2, at(20.0))
    state = race.to_dict()
    by_lane = {d['lane']: d for d in state['drivers']}
    assert by_lane[1]['has_started'] is False
    assert by_lane[1]['suspended'] is False


# --- FastestLap session type ---

def test_fastest_lap_session_target_laps_forced_high():
    race = new_race(target_laps=5, session_type='FastestLap', n_drivers=1)
    assert race.target_laps == 9999


def test_fastest_lap_session_tracks_session_fastest_per_driver():
    race = new_race(count_first_crossing=True, session_type='FastestLap', n_drivers=1)
    race.on_lap(1, at(5.0))
    race.on_lap(1, at(5.0 + 4.0))
    assert race.session_drivers[1]['session_fastest_lap'] == pytest.approx(4.0)


def test_fastest_lap_to_dict_includes_all_session_drivers_sorted_by_best():
    prior = [
        {'driver_id': 9, 'driver_name': 'Bench', 'session_fastest_lap': 3.5},
    ]
    race = new_race(count_first_crossing=True, session_type='FastestLap', n_drivers=1,
                     session_drivers=prior)
    race.on_lap(1, at(5.0))   # Driver1 laps in 5.0s, slower than Bench

    state = race.to_dict()
    assert state['session_type'] == 'FastestLap'
    names_in_order = [d['driver_name'] for d in state['session_drivers']]
    assert names_in_order == ['Bench', 'Driver1']

    bench = next(d for d in state['session_drivers'] if d['driver_name'] == 'Bench')
    assert bench['in_current_race'] is False
    assert bench['lane'] is None

    driver1 = next(d for d in state['session_drivers'] if d['driver_name'] == 'Driver1')
    assert driver1['in_current_race'] is True
    assert driver1['lane'] == 1
    assert driver1['current_race_laps'] == [pytest.approx(5.0)]


def test_fastest_lap_merge_preserves_better_in_memory_best_over_db_value():
    """_merge_session_drivers should keep the better of in-memory vs DB best,
    not blindly overwrite with whatever the API supplies."""
    race = new_race(count_first_crossing=True, session_type='FastestLap', n_drivers=1)
    race.on_lap(1, at(3.0))   # in-memory best = 3.0
    assert race.session_drivers[1]['session_fastest_lap'] == pytest.approx(3.0)

    # Reload lineup as if lapdata restarted mid-session and the API reports a
    # worse (higher) db_best for the same driver — in-memory value must win.
    race.load_lineup(
        race_id=2, race_number=2, target_laps=5,
        lane_assignments=make_lineup(1),
        count_first_crossing=True, session_type='FastestLap',
        session_drivers=[{'driver_id': 1, 'driver_name': 'Driver1', 'session_fastest_lap': 3.0}],
    )
    assert race.session_drivers[1]['session_fastest_lap'] == pytest.approx(3.0)
