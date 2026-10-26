"""plan_reconcile(): how one race_state message changes the DB (#79). DB-free."""
import pytest

from race_lifecycle import plan_reconcile

GO = 1749123456.789


def msg(state, race_id=5, race_start_time=GO):
    return {'state': state, 'race_id': race_id, 'race_start_time': race_start_time}


# --- The normal lifecycle ---

def test_armed_race_is_not_started_yet():
    assert plan_reconcile(msg('ArmedForStart', race_start_time=None), 'NotStarted', []) == []


@pytest.mark.parametrize('state', ['Running', 'Yellow', 'Paused'])
def test_a_race_under_way_is_started_with_lapdatas_lights_out(state):
    """Yellow and Paused too: a missed Running is repaired by whichever beat comes next."""
    assert plan_reconcile(msg(state), 'NotStarted', []) == [('start', 5, GO)]


def test_running_race_already_running_is_left_alone():
    """The heartbeat repeats Running every 2s."""
    assert plan_reconcile(msg('Running'), 'Running', [5]) == []


def test_finished_race_is_finished():
    assert plan_reconcile(msg('Finished'), 'Running', [5]) == [('finish', 5)]


def test_a_missed_running_is_started_before_it_is_finished():
    """So the session is promoted and started_at is stored."""
    assert plan_reconcile(msg('Finished'), 'NotStarted', []) == [('start', 5, GO), ('finish', 5)]


def test_ended_during_the_start_lights_is_finished_without_a_start():
    assert plan_reconcile(msg('Finished', race_start_time=None), 'NotStarted', []) == [('finish', 5)]


# --- Monotonic: never backwards ---

@pytest.mark.parametrize('state', ['ArmedForStart', 'Running', 'Yellow', 'Paused', 'Finished'])
def test_a_finished_race_is_never_reopened(state):
    assert plan_reconcile(msg(state), 'Finished', []) == []


def test_a_stale_message_for_a_finished_race_finishes_nothing_else():
    """A stale retained "Running, race 5" must not end race 6, which is really running."""
    assert plan_reconcile(msg('Running'), 'Finished', [6]) == []


def test_a_race_the_db_doesnt_have_changes_nothing():
    """A reseeded database: lapdata's race no longer exists."""
    assert plan_reconcile(msg('Running'), None, [3]) == []


# --- Narrow finish rule ---

@pytest.mark.parametrize('state', ['ArmedForStart', 'Running', 'Yellow', 'Paused'])
def test_a_different_race_under_way_finishes_the_old_one_first(state):
    actions = plan_reconcile(msg(state, race_id=6), 'NotStarted', [5])
    assert actions[0] == ('finish', 5)
    if state != 'ArmedForStart':
        assert actions[1:] == [('start', 6, GO)]


@pytest.mark.parametrize('race_state', [
    {'state': 'NotStarted', 'race_id': 6},
    {'state': 'NotStarted', 'race_id': None},
    {'state': 'Offline', 'race_id': None, 'drivers': []},
    {},
])
def test_nothing_is_inferred_from_an_idle_empty_or_offline_state(race_state):
    """lapdata publishes these before its startup recovery has run."""
    assert plan_reconcile(race_state, 'NotStarted', [5]) == []


def test_a_different_race_finished_does_not_finish_the_running_one():
    assert plan_reconcile(msg('Finished', race_id=6), 'Running', [5, 6]) == [('finish', 6)]
