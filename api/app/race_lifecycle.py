"""Race lifecycle persistence: a race's DB state follows lapdata's race_state (#79).

lapdata owns the live race and publishes it as a retained, heartbeated race_state. The
API's subscriber (race_state_subscriber.py) hands every one of those to reconcile(), which
compares it with the DB and fixes any difference. Level, not edge: nothing here remembers
the previous message, so a restarted subscriber, or a missed one, heals on the next beat.

plan_reconcile() is the decision and is DB-free, so it is unit-tested on its own
(test_race_lifecycle.py). The rules, all from #79:

- **Monotonic only.** NotStarted -> Running -> Finished, never backwards, so a stale
  "Running, race 5" can't reopen a race that was finished.
- **Narrow finish rule.** A race is finished only when race_state says Finished for that
  race, or when a *different* race is under way (so the old one must have ended).
  Nothing is inferred from an empty, NotStarted or Offline state: lapdata publishes one
  of those before its startup recovery has run.
- **Ordering.** The old race is finished (with its session auto-end check) before the
  new one is started.

A Finished race_state also carries each driver's final position and race time, which
are stored in driver_races as published (#81, plan_results()). ⚠️ A race finished by
inference (a different race under way) never had its Finished message reach us, so it
has no results.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from model import DriverRace, Race, RaceSession
from next_race import get_drivers_for_next_race_sql, remove_pending_races

logger = logging.getLogger('uvicorn.error')

# A race_state for a race that is under way: its lights-out has been scheduled, so any
# other race the DB still holds Running must have ended.
UNDER_WAY_STATES = ('ArmedForStart', 'Running', 'Yellow', 'Paused')
# States a race only reaches after lights-out (Finished can also follow an End during the
# start lights, which is why a Finished race with no start time skips the start step).
STARTED_STATES = ('Running', 'Yellow', 'Paused', 'Finished')


def plan_reconcile(race_state: dict, msg_race_db_state: Optional[str],
                   running_race_ids: list[int]) -> list[tuple]:
    """What to change in the DB to match one race_state message.

    `msg_race_db_state` is the DB state of the race the message names (None if the DB has
    no such race), `running_race_ids` every race the DB holds Running. Returns actions in
    the order to apply them: ('finish', race_id) or ('start', race_id, started_at)."""
    state = race_state.get('state')
    race_id = race_state.get('race_id')
    if race_id is None or state not in UNDER_WAY_STATES + ('Finished',):
        return []
    # Not a race the DB knows (a reseeded database), or one it has already finished: the
    # message is stale, and must not be used to finish anything else either.
    if msg_race_db_state not in ('NotStarted', 'Running'):
        return []

    actions = []
    if state in UNDER_WAY_STATES:
        actions += [('finish', other) for other in running_race_ids if other != race_id]

    db_state = msg_race_db_state
    started_at = race_state.get('race_start_time')
    if db_state == 'NotStarted' and state in STARTED_STATES and not (state == 'Finished' and started_at is None):
        actions.append(('start', race_id, started_at))
        db_state = 'Running'
    if state == 'Finished':
        actions.append(('finish', race_id))
    return actions


def plan_results(race_state: dict) -> Optional[dict]:
    """Each driver's result from a Finished race_state, as driver_id -> (position,
    race_time), or None if the message isn't a finished race.

    lapdata is the one authority on finishing position (#81), so these are copied as
    published, never re-ranked. A driver who never crossed the line is DNS: no position
    and no race time, so they score nothing."""
    if race_state.get('state') != 'Finished' or race_state.get('race_id') is None:
        return None
    return {
        d['driver_id']: ((d.get('position'), d.get('total_race_time'))
                         if d.get('has_started') else (None, None))
        for d in race_state.get('drivers') or []
        if d.get('driver_id') is not None
    }


def reconcile(dbsession: Session, race_state: dict) -> list[tuple]:
    """Bring the DB into line with one race_state. Returns the actions it applied."""
    race_id = race_state.get('race_id')
    race = dbsession.get(Race, race_id) if race_id is not None else None
    running = dbsession.exec(select(Race.id).where(Race.state == 'Running')).all()
    actions = plan_reconcile(race_state, race.state if race else None, list(running))
    for action in actions:
        if action[0] == 'finish':
            finish_race(dbsession, action[1])
            logger.info(f"race_state: race {action[1]} finished")
        else:
            start_race(dbsession, action[1], action[2])
            logger.info(f"race_state: race {action[1]} started")
    # Results too are level, not edge: any Finished race_state for a race the DB holds
    # Finished fills in whatever differs, so a result missed on the finishing beat is
    # stored on the next one. Lifecycle stays monotonic; only results are rewritten.
    results = plan_results(race_state)
    if results is not None and race is not None and race.state == 'Finished':
        if store_results(dbsession, race_id, results):
            logger.info(f"race_state: race {race_id} results stored")
    return actions


def store_results(dbsession: Session, race_id: int, results: dict) -> bool:
    """Write lapdata's positions and race times to driver_races, touching only rows that
    differ (the heartbeat repeats Finished every 2s). Returns True if anything changed."""
    changed = False
    for dr in dbsession.exec(select(DriverRace).where(DriverRace.race_id == race_id)).all():
        if dr.driver_id not in results:
            continue
        position, race_time = results[dr.driver_id]
        race_time = Decimal(str(race_time)).quantize(Decimal('0.001')) if race_time is not None else None
        if dr.position != position or dr.race_time != race_time:
            dr.position, dr.race_time = position, race_time
            dbsession.add(dr)
            changed = True
    if changed:
        dbsession.commit()
    return changed


def start_race(dbsession: Session, race_id: int, started_at: Optional[float]) -> bool:
    """NotStarted -> Running, promoting the session to InProgress if it hasn't been.
    `started_at` is lapdata's lights-out (race_state.race_start_time, unix seconds).
    Anything but NotStarted is left alone, so a stale message can't reopen a finished
    race. Returns False if there is no such race."""
    race = dbsession.get(Race, race_id)
    if not race:
        return False
    if race.state != 'NotStarted':
        return True
    race.state = 'Running'
    if started_at is not None:
        race.started_at = datetime.fromtimestamp(started_at, tz=timezone.utc)
    dbsession.add(race)
    session = dbsession.get(RaceSession, race.session_id)
    if session and session.state == 'NotStarted':
        session.state = 'InProgress'
        dbsession.add(session)
    dbsession.commit()
    return True


def finish_race(dbsession: Session, race_id: int) -> bool:
    """-> Finished, then the session auto-end: a session with a races_per_driver target
    ends once no active driver is still short of it. Ending is automatic; starting the
    next session stays a manual /racecontrol action, so nothing is promoted here. A race
    that is already Finished is left alone (the heartbeat repeats Finished every 2s).
    Returns False if there is no such race."""
    race = dbsession.get(Race, race_id)
    if not race:
        return False
    if race.state == 'Finished':
        return True
    race.state = 'Finished'
    dbsession.add(race)
    dbsession.commit()
    session = dbsession.get(RaceSession, race.session_id)
    if session and session.races_per_driver:
        target = session.races_per_driver
        all_drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=session.id)
        eligible = [d for d in all_drivers
                    if not d.sit_out_next_race and not d.disqualified and d.completed_races < target]
        if not eligible:
            session.state = 'Finished'
            dbsession.add(session)
            dbsession.commit()
            # No NotStarted race may outlive a Finished session.
            remove_pending_races(dbsession, session.id)
    return True
