import pytest
from race_manager import RaceManager


def make_lineup(n=3):
    """lane_assignments for lanes 1..n, driver_id = lane, named DriverN."""
    return [
        {'id': lane, 'driver_name': f'Driver{lane}', 'lane_number': lane}
        for lane in range(1, n + 1)
    ]


def new_race(target_laps=3, count_first_crossing=False, n_drivers=3, session_type='Points',
             race_duration_seconds=None, session_drivers=None):
    race = RaceManager()
    race.load_lineup(
        race_id=1, race_number=1, target_laps=target_laps,
        lane_assignments=make_lineup(n_drivers),
        count_first_crossing=count_first_crossing,
        session_type=session_type,
        race_duration_seconds=race_duration_seconds,
        session_drivers=session_drivers,
    )
    race.start()
    return race


# --- Discarded first crossing (CLAUDE.md-documented footgun) ---

def test_discarded_first_crossing_not_counted_as_lap():
    race = new_race(count_first_crossing=False)
    race.on_lap(1, race.race_start_time + 0.5)
    driver = race.drivers[1]
    assert driver.laps_completed == 0
    assert driver.crossings == 1


def test_discarded_first_crossing_still_sets_last_crossing_time():
    """Regression test: last_crossing_time must be set even when the first
    crossing is discarded, or race_time() silently returns 0.0 and position
    sort falls back to lane-number order instead of crossing order."""
    race = new_race(count_first_crossing=False)
    crossing_time = race.race_start_time + 0.5
    race.on_lap(1, crossing_time)
    driver = race.drivers[1]
    assert driver.last_crossing_time == crossing_time
    assert driver.race_time(race.race_start_time) == pytest.approx(0.5)


def test_count_first_crossing_true_counts_lap_one():
    race = new_race(count_first_crossing=True)
    race.on_lap(1, race.race_start_time + 5.0)
    driver = race.drivers[1]
    assert driver.laps_completed == 1
    assert driver.last_lap_time == pytest.approx(5.0)


# --- Lap timing ---

def test_lap_one_timed_from_race_start():
    race = new_race(count_first_crossing=True)
    race.on_lap(1, race.race_start_time + 4.5)
    assert race.drivers[1].last_lap_time == pytest.approx(4.5)


def test_subsequent_laps_timed_from_previous_crossing():
    race = new_race(count_first_crossing=True)
    race.on_lap(1, race.race_start_time + 4.5)
    race.on_lap(1, race.race_start_time + 9.0)
    driver = race.drivers[1]
    assert driver.laps_completed == 2
    assert driver.last_lap_time == pytest.approx(4.5)
    assert driver.lap_times == [pytest.approx(4.5), pytest.approx(4.5)]


def test_discarded_crossing_then_first_real_lap_still_timed_from_race_start():
    """Lap 1 is always timed from lights-out, even after a discarded crossing —
    the discard only affects lap *counting*, not the lap-1 timing base."""
    race = new_race(count_first_crossing=False)
    race.on_lap(1, race.race_start_time + 0.5)   # discarded
    race.on_lap(1, race.race_start_time + 5.0)   # lap 1: real
    driver = race.drivers[1]
    assert driver.laps_completed == 1
    assert driver.last_lap_time == pytest.approx(5.0)


# --- Fastest lap tracking ---

def test_best_lap_and_race_fastest_lap_tracked():
    race = new_race(count_first_crossing=True, n_drivers=2)
    race.on_lap(1, race.race_start_time + 5.0)
    race.on_lap(2, race.race_start_time + 4.0)
    race.on_lap(1, race.race_start_time + 5.0 + 4.5)
    assert race.drivers[1].best_lap_time == pytest.approx(4.5)
    assert race.drivers[2].best_lap_time == pytest.approx(4.0)
    assert race.race_fastest_lap == pytest.approx(4.0)


# --- Ignored crossings ---

def test_on_lap_ignored_when_not_running():
    race = new_race(count_first_crossing=True)
    race.pause()
    updated = race.on_lap(1, race.race_start_time + 5.0)
    assert updated is False
    assert race.drivers[1].laps_completed == 0


def test_on_lap_ignored_for_unknown_lane():
    race = new_race(count_first_crossing=True, n_drivers=2)
    updated = race.on_lap(5, race.race_start_time + 5.0)
    assert updated is False


def test_on_lap_ignored_once_driver_finished():
    race = new_race(target_laps=1, count_first_crossing=True, n_drivers=2)
    race.on_lap(1, race.race_start_time + 5.0)
    assert race.drivers[1].finished is True
    updated = race.on_lap(1, race.race_start_time + 10.0)
    assert updated is False
    assert race.drivers[1].laps_completed == 1


# --- Chequered flag / race end ---

def test_other_drivers_finish_on_their_next_crossing_after_winner():
    """A driver who has already started (crossed at least once) keeps the race
    open until their next crossing, even after someone else hits the target —
    this is what gives trailing-but-running drivers one more lap."""
    race = new_race(target_laps=2, count_first_crossing=True, n_drivers=2)
    race.on_lap(2, race.race_start_time + 5.0)    # driver 2 has started (lap 1)
    race.on_lap(1, race.race_start_time + 5.0)
    race.on_lap(1, race.race_start_time + 10.0)   # driver 1 wins, finishes
    assert race.drivers[1].finished is True
    assert race.drivers[2].finished is False
    assert race.state == 'Running'                # driver 2 has started, not yet finished

    race.on_lap(2, race.race_start_time + 9.0)     # driver 2's next crossing
    assert race.drivers[2].finished is True
    assert race.drivers[2].laps_completed == 2
    assert race.state == 'Finished'


def test_race_ends_when_all_started_drivers_finished():
    race = new_race(target_laps=2, count_first_crossing=True, n_drivers=2)
    race.on_lap(2, race.race_start_time + 5.0)    # driver 2 has started
    race.on_lap(1, race.race_start_time + 5.0)
    race.on_lap(1, race.race_start_time + 10.0)   # driver 1 finishes
    assert race.state == 'Running'                # driver 2 started, hasn't finished yet
    race.on_lap(2, race.race_start_time + 9.0)
    assert race.state == 'Finished'


def test_race_ends_when_remaining_drivers_never_started():
    """A driver who never crosses the line at all doesn't block race end."""
    race = new_race(target_laps=1, count_first_crossing=True, n_drivers=2)
    race.on_lap(1, race.race_start_time + 5.0)
    assert race.drivers[1].finished is True
    assert race.state == 'Finished'  # driver 2 never started, doesn't block


# --- to_dict / position sorting ---

def test_to_dict_sorted_by_laps_then_started_then_race_time_but_output_sorted_by_lane():
    race = new_race(target_laps=5, count_first_crossing=True, n_drivers=3)
    race.on_lap(1, race.race_start_time + 5.0)   # lane 1: 1 lap
    race.on_lap(2, race.race_start_time + 5.0)   # lane 2: 1 lap
    race.on_lap(2, race.race_start_time + 9.0)   # lane 2: 2 laps (ahead)
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
    race.on_lap(1, race.race_start_time + 4.321)
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
    race.on_lap(1, race.race_start_time + 5.0)
    race.on_lap(2, race.race_start_time + 5.0)
    race.on_lap(2, race.race_start_time + 20.0)   # lane 2 pulls well ahead in race_time

    state = race.to_dict()
    by_lane = {d['lane']: d for d in state['drivers']}
    assert by_lane[1]['suspended'] is True
    assert by_lane[2]['suspended'] is False


def test_driver_never_crossed_not_suspended():
    race = new_race(target_laps=10, count_first_crossing=True, n_drivers=2)
    race.on_lap(2, race.race_start_time + 20.0)
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
    race.on_lap(1, race.race_start_time + 5.0)
    race.on_lap(1, race.race_start_time + 5.0 + 4.0)
    assert race.session_drivers[1]['session_fastest_lap'] == pytest.approx(4.0)


def test_fastest_lap_to_dict_includes_all_session_drivers_sorted_by_best():
    prior = [
        {'driver_id': 9, 'driver_name': 'Bench', 'session_fastest_lap': 3.5},
    ]
    race = new_race(count_first_crossing=True, session_type='FastestLap', n_drivers=1,
                     session_drivers=prior)
    race.on_lap(1, race.race_start_time + 5.0)   # Driver1 laps in 5.0s, slower than Bench

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
    race.on_lap(1, race.race_start_time + 3.0)   # in-memory best = 3.0
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
