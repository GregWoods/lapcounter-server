import logging
import math
import traceback
import random
from collections import Counter
from datetime import date as date_type
from typing import List
from fastapi import HTTPException
from sqlmodel import select
from model import *
from responsemodel import NextRaceSetup, DriverWithLane, RaceSessionWithState, SessionDriverFastestLap
from pprint import pprint


logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)


def get_drivers_for_next_race_sql(dbsession, race_session_id: int):
    try:
        from sqlalchemy import text
        query = text("""
            SELECT
                d.id,
                md.driver_name,
                d.sit_out_next_race,
                COALESCE(sd.disqualified, FALSE) as disqualified,
                COUNT(r.id) as completed_races,
                COUNT(CASE WHEN dr.lane = 1 THEN 1 END) as lane1_count,
                COUNT(CASE WHEN dr.lane = 2 THEN 1 END) as lane2_count,
                COUNT(CASE WHEN dr.lane = 3 THEN 1 END) as lane3_count,
                COUNT(CASE WHEN dr.lane = 4 THEN 1 END) as lane4_count,
                COUNT(CASE WHEN dr.lane = 5 THEN 1 END) as lane5_count,
                COUNT(CASE WHEN dr.lane = 6 THEN 1 END) as lane6_count,
                RANDOM() as random_value
            FROM
                drivers d
            LEFT JOIN
                meeting_drivers md ON d.id = md.driver_id
            LEFT JOIN
                driver_races dr ON d.id = dr.driver_id
            LEFT JOIN
                races r ON dr.race_id = r.id AND r.state = 'Finished' AND r.session_id = :session_id
            LEFT JOIN
                session_drivers sd ON d.id = sd.driver_id AND sd.session_id = :session_id
            GROUP BY
                d.id, md.driver_name, d.sit_out_next_race, sd.disqualified
            ORDER BY
                sit_out_next_race ASC,
                completed_races ASC,
                random_value ASC
        """)
        rows = dbsession.exec(query.bindparams(session_id=race_session_id)).all()
        # Convert SQL rows to DriverWithLane objects
        drivers = []
        for row in rows:
            driver = DriverWithLane(
                id=row.id,
                driver_name=row.driver_name,
                sit_out_next_race=row.sit_out_next_race,
                disqualified=row.disqualified,
                completed_races=row.completed_races,
                lane1_count=row.lane1_count,
                lane2_count=row.lane2_count,
                lane3_count=row.lane3_count,
                lane4_count=row.lane4_count,
                lane5_count=row.lane5_count,
                lane6_count=row.lane6_count,
                random_value=row.random_value
            )
            drivers.append(driver)
        return drivers
    except Exception as e:
        logger.error(f"Error retrieving drivers for next race: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)


#The unit-testable logic for sorting drivers into racing and non-racing groups
#  No dependencies on the database or the api routing magic
def assign_drivers_to_lanes(driver_list: List[DriverWithLane], lanes: List[Lane]):
    """
    Assign drivers to lanes for the next race, optimizing lane assignments.
    
    Args:
        driver_list: List of DriverWithLane objects from the database
        lanes: List of Lane objects representing physical lanes
        
    Returns:
        NextRaceSetup with racing drivers assigned to lanes and remaining drivers
    """
    # Create a copy of driver_list that we can modify
    available_drivers = list(driver_list)

    # Sort available_drivers using the same logic as the SQL query
    #   We need to do it here for the unit tests to work correctly.
    available_drivers.sort(key=lambda d: (
        d.sit_out_next_race,  # Sort by sit_out_next_race (False comes before True)
        d.completed_races,    # Then by completed_races (ascending)
        d.random_value        # Then by random value (ascending)
    ))

    # Get enabled lanes and determine how many drivers we need
    enabled_lanes = [lane for lane in lanes if lane.enabled]

    # Get all drivers who aren't sitting out or disqualified from the session
    available_racing_drivers = [d for d in available_drivers
                                if not d.sit_out_next_race and not d.disqualified]
    
    # Determine how many drivers we need (min of enabled lanes and available available_racing_drivers)
    num_racing_drivers = min(len(enabled_lanes), len(available_racing_drivers))

    # Take the top N drivers who aren't sitting out, sorted by completed_races
    # (they're already sorted by completed_races from the SQL query)
    racing_drivers = available_racing_drivers[:num_racing_drivers]

    # All other drivers go into drivers_not_racing
    racing_driver_ids = {d.id for d in racing_drivers}
    drivers_not_racing = [d for d in available_drivers if d.id not in racing_driver_ids]

    # Create a list of blank drivers with lanes
    lane_assignments = []
    for lane in lanes:
        lane_assignments.append(DriverWithLane.create(lane=lane))
    random.shuffle(lane_assignments)

    # assign drivers to lane
    for lane in lane_assignments:
        if lane.lane_enabled is False:
            continue
        # get a driver who has used this lane the least number of times
        racing_drivers.sort(key=lambda driver: getattr(driver, f"lane{lane.lane_number}_count"))
        #lanes_with_drivers.append(DriverWithLane.create(driver=racing_drivers.pop(0), lane))
        if len(racing_drivers) > 0:
            lane.add_driver_to_lane(racing_drivers.pop(0))

    # Sort lanes_with_drivers by lane number
    lane_assignments.sort(key=lambda driver: driver.lane_number)

    # Order other_drivers by completed_races only... once we've filled all the lanes
    #   we don't care if they are sitting out or not.
    drivers_not_racing.sort(key=lambda driver: driver.completed_races)

    return NextRaceSetup(
        lane_assignments=lane_assignments,
        other_drivers=drivers_not_racing
    )


def get_session_fastest_laps(dbsession, session_id: int) -> list:
    """Return all session drivers with their best lap time across finished races.

    Returns [] for non-FastestLap contexts. Until the DB writer is implemented
    all session_fastest_lap values will be None (no DriverLap records exist in
    production), but the list of drivers is correct for initialising LapData's
    in-memory session state.
    """
    from sqlalchemy import text
    query = text("""
        SELECT
            d.id            AS driver_id,
            md.driver_name,
            MIN(dl.lap_time) AS session_fastest_lap
        FROM sessions s
        JOIN meeting_drivers md ON s.meeting_id = md.meeting_id
        JOIN drivers d ON d.id = md.driver_id
        LEFT JOIN driver_races dr
            ON d.id = dr.driver_id
            AND dr.race_id IN (
                SELECT id FROM races
                WHERE session_id = :session_id AND state = 'Finished'
            )
        LEFT JOIN driver_laps dl ON dl.driver_race_id = dr.id
        WHERE s.id = :session_id
        GROUP BY d.id, md.driver_name
        ORDER BY session_fastest_lap ASC NULLS LAST
    """)
    rows = dbsession.exec(query.bindparams(session_id=session_id)).all()
    return [
        SessionDriverFastestLap(
            driver_id=row.driver_id,
            driver_name=row.driver_name,
            session_fastest_lap=float(row.session_fastest_lap) if row.session_fastest_lap is not None else None,
        )
        for row in rows
    ]


def compute_session_progress(race_session, all_drivers, dbsession):
    """For sessions with a races_per_driver target, return (races_done, projected_total).
    Else (0, None)."""
    R = race_session.races_per_driver or 0
    if not R:
        return 0, None
    enabled_lanes = dbsession.exec(select(Lane).where(Lane.enabled == True)).all()
    L = max(1, len(enabled_lanes))
    races_done = len(dbsession.exec(
        select(Race).where(Race.session_id == race_session.id, Race.state == 'Finished')
    ).all())
    active = [d for d in all_drivers if not d.sit_out_next_race and not d.disqualified]
    remaining_slots = sum(max(0, R - d.completed_races) for d in active)
    effective_L = min(len(active), L)
    races_remaining = math.ceil(remaining_slots / effective_L) if remaining_slots > 0 and effective_L > 0 else 0
    return races_done, races_done + races_remaining


def select_balanced_race_drivers(race_session, drivers, lanes):
    """Pick the drivers for the next race so the session ends with every driver having
    raced exactly ``races_per_driver`` times, without a tiny final race.

    Returns ``(selected_drivers, session_complete)``. When ``session_complete`` is True
    every active driver has reached the target and no race should be staged.

    Strategy "balance race sizes": spread the remaining driver-slots over the fewest
    races (``ceil(slots / lanes)``) and make each remaining race as equal as possible,
    so later races shrink evenly instead of draining down to one or two stragglers.
    Drivers are taken fewest-raced first (``drivers`` arrives pre-sorted from SQL).
    """
    R = race_session.races_per_driver or 0
    if not R:
        return drivers, False

    active_under = [d for d in drivers
                    if not d.sit_out_next_race and not d.disqualified and d.completed_races < R]
    if not active_under:
        return [], True

    L = max(1, len([l for l in lanes if l.enabled]))
    remaining_slots = sum(R - d.completed_races for d in active_under)
    remaining_races = math.ceil(remaining_slots / L)
    size = math.ceil(remaining_slots / remaining_races)
    size = min(size, len(active_under), L)
    return active_under[:size], False


def get_active_meeting(dbsession):
    """Return the earliest meeting with date >= today. Raises 404 if none found."""
    today = date_type.today()
    meeting = dbsession.exec(
        select(Meeting).where(Meeting.date >= today).order_by(Meeting.date.asc())
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="No active or upcoming meetings found")
    return meeting


def get_active_meeting_id(dbsession):
    return get_active_meeting(dbsession).id


def get_active_session(dbsession):
    """Return the active race session for the active meeting.

    Priority:
    1. Most recent InProgress session (race day is underway).
    2. Earliest NotStarted session (next one coming up — multiple may be pre-planned).
    Finished sessions are never returned.
    """
    meeting_id = get_active_meeting_id(dbsession)

    in_progress = dbsession.exec(
        select(RaceSession)
        .where(RaceSession.meeting_id == meeting_id, RaceSession.state == 'InProgress')
        .order_by(RaceSession.id.desc())
    ).first()
    if in_progress:
        return in_progress

    not_started = dbsession.exec(
        select(RaceSession)
        .where(RaceSession.meeting_id == meeting_id, RaceSession.state == 'NotStarted')
        .order_by(RaceSession.id.asc())
    ).first()
    if not_started:
        return not_started

    raise HTTPException(status_code=404, detail="No active or upcoming sessions found for this meeting")


def get_session_for_results(dbsession):
    """Return the session whose results should be shown by default.

    Prefers the active session (InProgress / NotStarted). Once a meeting is over
    and every session is Finished, falls back to the most recently finished
    session so results stay viewable after the session ends.
    """
    try:
        return get_active_session(dbsession)
    except HTTPException:
        meeting_id = get_active_meeting_id(dbsession)
        finished = dbsession.exec(
            select(RaceSession)
            .where(RaceSession.meeting_id == meeting_id, RaceSession.state == 'Finished')
            .order_by(RaceSession.id.desc())
        ).first()
        if finished:
            return finished
        raise


def compute_session_state(races) -> str:
    if not races:
        return 'NotStarted'
    if all(r.state == 'Finished' for r in races):
        return 'Finished'
    if all(r.state == 'NotStarted' for r in races):
        return 'NotStarted'
    return 'InProgress'


def session_with_state(race_session, dbsession) -> RaceSessionWithState:
    return RaceSessionWithState(**race_session.model_dump())


def find_pending_race(dbsession):
    """Return the *next* NotStarted race in the active session, or None.

    A session now holds an ordered queue of NotStarted races (the whole session is
    pre-populated when it starts). The earliest by race_number is the one to run
    next — the "current" race once nothing is Running.
    """
    try:
        active_session = get_active_session(dbsession)
    except HTTPException:
        return None
    return dbsession.exec(
        select(Race)
        .where(Race.state == 'NotStarted', Race.session_id == active_session.id)
        .order_by(Race.race_number, Race.id)
    ).first()


def load_race_queue(dbsession):
    """Read-only: the ordered list of upcoming (NotStarted) race setups for the active
    session — the head is the next race, the tail is the lookahead the NextRace page
    previews. Empty when no session is in progress or the queue is exhausted."""
    try:
        active_session = get_active_session(dbsession)
    except HTTPException:
        return []
    races = dbsession.exec(
        select(Race)
        .where(Race.state == 'NotStarted', Race.session_id == active_session.id)
        .order_by(Race.race_number, Race.id)
    ).all()
    return [setup for setup in (_build_race_setup(dbsession, r) for r in races) if setup]


def load_pending_race(dbsession):
    """Load the existing NotStarted race from DB. Returns NextRaceSetup or None."""
    pending_race = find_pending_race(dbsession)
    if not pending_race:
        return None

    # Recalculate race_number from current DB state so it stays accurate regardless
    # of when the pending race was created. Also counts earlier NotStarted (queued)
    # races so numbers stay correct when multiple races are queued in advance.
    preceding_count = len(dbsession.exec(
        select(Race).where(
            Race.session_id == pending_race.session_id,
            (Race.state.in_(['Finished', 'Running'])) |
            ((Race.state == 'NotStarted') & (Race.id < pending_race.id))
        )
    ).all())
    correct_number = preceding_count + 1
    if pending_race.race_number != correct_number:
        pending_race.race_number = correct_number
        dbsession.add(pending_race)
        dbsession.commit()

    has_lineup = dbsession.exec(
        select(DriverRace).where(DriverRace.race_id == pending_race.id)
    ).first()

    # Stale race with no lineup (e.g. from sample data) — delete and recalculate
    if not has_lineup:
        dbsession.delete(pending_race)
        dbsession.commit()
        return None

    return _build_race_setup(dbsession, pending_race)


def find_current_race(dbsession):
    """Return the Running race in the active session, or None.

    The DB is authoritative for *which* race is current; lapdata's race_state is a
    live overlay the client applies only when its race_id matches.
    """
    try:
        active_session = get_active_session(dbsession)
    except HTTPException:
        return None
    return dbsession.exec(
        select(Race)
        .where(Race.state == 'Running', Race.session_id == active_session.id)
        .order_by(Race.id.desc())
    ).first()


def load_current_race(dbsession):
    """Setup for the Running race if one exists, else None (the caller falls back
    to the pending race)."""
    running = find_current_race(dbsession)
    if not running:
        return None
    return _build_race_setup(dbsession, running)


def _build_race_setup(dbsession, race):
    """Build a NextRaceSetup response from a Race (pending or running).

    Returns None if the race has no lineup. Shared by load_pending_race and
    load_current_race so the pending and running views are built identically.
    """
    driver_races = dbsession.exec(
        select(DriverRace).where(DriverRace.race_id == race.id)
    ).all()
    if not driver_races:
        return None

    lanes_list = dbsession.exec(select(Lane).order_by(Lane.lane_number)).all()

    assigned_driver_ids = {dr.driver_id for dr in driver_races}
    driver_race_by_lane = {dr.lane: dr for dr in driver_races}

    # Map car_id → picture for the cars assigned to this race's lanes
    car_ids = {dr.car_id for dr in driver_races if dr.car_id is not None}
    car_pictures = {}
    if car_ids:
        car_rows = dbsession.exec(select(Car).where(Car.id.in_(car_ids))).all()
        car_pictures = {c.id: c.picture for c in car_rows}

    # Reuse existing SQL for driver stats (lane counts, completed_races, etc.)
    all_drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=race.session_id)
    all_drivers_map = {d.id: d for d in all_drivers}

    # Get meeting-specific display names
    race_session = dbsession.get(RaceSession, race.session_id)
    md_rows = dbsession.exec(
        select(MeetingDriver).where(MeetingDriver.meeting_id == race_session.meeting_id)
    ).all()
    meeting_driver_names = {md.driver_id: md.driver_name for md in md_rows}

    # Build lane_assignments — one slot per lane
    lane_assignments = []
    for lane in lanes_list:
        if lane.lane_number in driver_race_by_lane:
            dr = driver_race_by_lane[lane.lane_number]
            driver_stats = all_drivers_map.get(dr.driver_id)
            if driver_stats:
                dwl = DriverWithLane.create(driver=driver_stats, lane=lane)
                dwl.driver_name = meeting_driver_names.get(dr.driver_id, driver_stats.driver_name)
            else:
                dwl = DriverWithLane.create(lane=lane)
                dwl.id = dr.driver_id
                dwl.driver_name = meeting_driver_names.get(dr.driver_id, "")
            dwl.car_picture = car_pictures.get(dr.car_id, "")
        else:
            dwl = DriverWithLane.create(lane=lane)
        lane_assignments.append(dwl)

    other_drivers = [d for d in all_drivers if d.id not in assigned_driver_ids]
    other_drivers.sort(key=lambda d: d.completed_races)

    meeting = dbsession.get(Meeting, race_session.meeting_id)
    count_first_crossing = meeting.count_first_crossing if meeting else False

    # 1-based ordinal of this session within its meeting (matches the Results tabs).
    meeting_session_ids = list(dbsession.exec(
        select(RaceSession.id)
        .where(RaceSession.meeting_id == race_session.meeting_id)
        .order_by(RaceSession.id)
    ).all())
    session_number = (meeting_session_ids.index(race_session.id) + 1
                      if race_session.id in meeting_session_ids else None)

    races_done, races_total = compute_session_progress(race_session, all_drivers, dbsession)

    race_duration_seconds = None
    if race_session.end_condition == 'Time' and race_session.end_condition_info:
        race_duration_seconds = race_session.end_condition_info * 60

    session_drivers = []
    if race_session.session_type == 'FastestLap':
        session_drivers = get_session_fastest_laps(dbsession, race_session.id)

    return NextRaceSetup(
        race_id=race.id,
        race_number=race.race_number or 1,
        session_number=session_number,
        count_first_crossing=count_first_crossing,
        lane_assignments=lane_assignments,
        other_drivers=other_drivers,
        session_races_done=races_done,
        session_races_total=races_total,
        session_type=race_session.session_type,
        race_duration_seconds=race_duration_seconds,
        session_drivers=session_drivers,
    )


def get_car_id_for_lane(dbsession, lane_number: int, meeting_id: int):
    """Return car_id for a lane: last finished race first, then meeting_cars default."""
    session_ids = [s.id for s in dbsession.exec(
        select(RaceSession).where(RaceSession.meeting_id == meeting_id)
    ).all()]
    last_race = dbsession.exec(
        select(Race)
        .where(Race.session_id.in_(session_ids), Race.state == 'Finished')
        .order_by(Race.id.desc())
    ).first()
    if last_race:
        dr = dbsession.exec(
            select(DriverRace).where(
                DriverRace.race_id == last_race.id,
                DriverRace.lane == lane_number
            )
        ).first()
        if dr and dr.car_id is not None:
            return dr.car_id
    meeting_car = dbsession.exec(
        select(MeetingCar).where(
            MeetingCar.meeting_id == meeting_id,
            MeetingCar.lane == lane_number
        )
    ).first()
    return meeting_car.car_id if meeting_car else None


def add_driver_to_pending_lineup(dbsession, pending_race, driver_id: int):
    """Add a driver to the pending race on their best available enabled lane."""
    existing = dbsession.exec(
        select(DriverRace).where(DriverRace.race_id == pending_race.id)
    ).all()
    if any(dr.driver_id == driver_id for dr in existing):
        raise HTTPException(status_code=400, detail="Driver already in this race")
    occupied_lanes = {dr.lane for dr in existing}
    lanes = dbsession.exec(select(Lane).order_by(Lane.lane_number)).all()
    free_lanes = [l for l in lanes if l.enabled and l.lane_number not in occupied_lanes]
    if not free_lanes:
        raise HTTPException(status_code=400, detail="No free lanes available")
    all_drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=pending_race.session_id)
    driver_data = next((d for d in all_drivers if d.id == driver_id), None)
    if not driver_data:
        raise HTTPException(status_code=404, detail="Driver not found")
    best_lane = min(free_lanes, key=lambda l: getattr(driver_data, f"lane{l.lane_number}_count"))
    race_session = dbsession.get(RaceSession, pending_race.session_id)
    car_id = get_car_id_for_lane(dbsession, best_lane.lane_number, race_session.meeting_id)
    dbsession.add(DriverRace(
        driver_id=driver_id,
        race_id=pending_race.id,
        car_id=car_id,
        lane=best_lane.lane_number,
    ))
    dbsession.commit()
    # Re-adding a driver to this race cancels any earlier withdrawal (it wasn't a skip).
    clear_withdrawal(dbsession, pending_race.id, driver_id)
    # Re-instating a disqualified driver undoes their session DQ and resets their skip
    # tally, so the "sat out too many races" prompt doesn't fire again on a deliberate return.
    if driver_data.disqualified:
        set_driver_disqualified(dbsession, pending_race.session_id, driver_id, False)
        clear_session_withdrawals(dbsession, pending_race.session_id, driver_id)
    return load_pending_race(dbsession)


def record_withdrawal(dbsession, race_id: int, driver_id: int):
    """Record that the operator removed a driver from a race (the NextRace "×"). Idempotent."""
    existing = dbsession.get(RaceWithdrawal, (race_id, driver_id))
    if not existing:
        dbsession.add(RaceWithdrawal(race_id=race_id, driver_id=driver_id))
        dbsession.commit()


def clear_withdrawal(dbsession, race_id: int, driver_id: int):
    """Undo a withdrawal — the driver has been re-added to that race, so it isn't a skip."""
    existing = dbsession.get(RaceWithdrawal, (race_id, driver_id))
    if existing:
        dbsession.delete(existing)
        dbsession.commit()


def clear_session_withdrawals(dbsession, session_id: int, driver_id: int):
    """Drop every withdrawal a driver has accrued in a session — resets their skip tally.

    Used when the operator deliberately brings a driver back (reinstate, or re-adding them
    in NextRace) so the "sat out too many races" prompt doesn't immediately fire again on
    what is now an intentional return."""
    race_ids = [r.id for r in dbsession.exec(
        select(Race).where(Race.session_id == session_id)
    ).all()]
    if not race_ids:
        return
    withdrawals = dbsession.exec(
        select(RaceWithdrawal).where(
            RaceWithdrawal.driver_id == driver_id,
            RaceWithdrawal.race_id.in_(race_ids),
        )
    ).all()
    for w in withdrawals:
        dbsession.delete(w)
    if withdrawals:
        dbsession.commit()


def session_skip_counts(dbsession, session_id: int) -> dict:
    """Map driver_id -> cumulative skips for a session: withdrawals attached to the
    session's *Finished* races. A withdrawal on a NotStarted race doesn't count yet (the
    race hasn't run), which is what makes skips effectively counted at race-finish time."""
    from sqlalchemy import text
    query = text("""
        SELECT w.driver_id AS driver_id, COUNT(*) AS skips
        FROM race_withdrawals w
        JOIN races r ON r.id = w.race_id
        WHERE r.session_id = :session_id AND r.state = 'Finished'
        GROUP BY w.driver_id
    """)
    rows = dbsession.exec(query.bindparams(session_id=session_id)).all()
    return {row.driver_id: row.skips for row in rows}


def set_driver_disqualified(dbsession, session_id: int, driver_id: int, disqualified: bool):
    """Upsert the per-session disqualified flag for a driver."""
    sd = dbsession.get(SessionDriver, (session_id, driver_id))
    if sd:
        sd.disqualified = disqualified
        dbsession.add(sd)
    else:
        dbsession.add(SessionDriver(
            session_id=session_id, driver_id=driver_id, disqualified=disqualified
        ))
    dbsession.commit()


def set_lane_enabled(dbsession, lane_number: int, enabled: bool):
    """Enable or disable a lane and update the pending race lineup accordingly."""
    lane = dbsession.get(Lane, lane_number)
    if not lane:
        raise HTTPException(status_code=404, detail="Lane not found")

    lane.enabled = enabled
    dbsession.add(lane)
    dbsession.commit()

    pending_race = find_pending_race(dbsession)
    if not pending_race:
        return load_pending_race(dbsession)

    if not enabled:
        driver_race = dbsession.exec(
            select(DriverRace).where(
                DriverRace.race_id == pending_race.id,
                DriverRace.lane == lane_number
            )
        ).first()
        if driver_race:
            dbsession.delete(driver_race)
            dbsession.commit()
    else:
        existing = dbsession.exec(
            select(DriverRace).where(DriverRace.race_id == pending_race.id)
        ).all()
        assigned_ids = {dr.driver_id for dr in existing}
        race_session = dbsession.get(RaceSession, pending_race.session_id)
        quota = race_session.races_per_driver if race_session else None

        all_drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=pending_race.session_id)
        next_driver = next(
            (d for d in all_drivers
             if not d.sit_out_next_race
             and not d.disqualified
             and d.id not in assigned_ids
             and (quota is None or d.completed_races < quota)),
            None
        )

        if next_driver:
            car_id = get_car_id_for_lane(dbsession, lane_number, race_session.meeting_id)
            dbsession.add(DriverRace(
                driver_id=next_driver.id,
                race_id=pending_race.id,
                car_id=car_id,
                lane=lane_number,
            ))
            dbsession.commit()
            # Auto-filling this driver back in cancels any withdrawal on this race.
            clear_withdrawal(dbsession, pending_race.id, next_driver.id)

    return load_pending_race(dbsession)


def recalculate_meeting_driver_names(dbsession, meeting_id: int):
    """Recompute disambiguated driver_name for every driver in a meeting.

    Normally just first_name. Adds last initial when two drivers share a first name,
    e.g. two drivers named Jake become 'Jake W' and 'Jake H'.
    """
    meeting_drivers = dbsession.exec(
        select(MeetingDriver).where(MeetingDriver.meeting_id == meeting_id)
    ).all()
    if not meeting_drivers:
        return

    driver_ids = [md.driver_id for md in meeting_drivers]
    drivers = dbsession.exec(select(Driver).where(Driver.id.in_(driver_ids))).all()
    driver_map = {d.id: d for d in drivers}

    first_name_counts = Counter(
        driver_map[md.driver_id].first_name.lower()
        for md in meeting_drivers
        if md.driver_id in driver_map
    )

    for md in meeting_drivers:
        driver = driver_map.get(md.driver_id)
        if not driver:
            continue
        if first_name_counts[driver.first_name.lower()] > 1 and driver.last_name:
            md.driver_name = f"{driver.first_name} {driver.last_name[0].upper()}"
        else:
            md.driver_name = driver.first_name
        dbsession.add(md)

    dbsession.commit()


def _lane_to_car_map(dbsession, meeting_id):
    """Resolve lane → car_id for a new race lineup in this meeting.

    Primary source is the last completed race (cars stay on their lanes between
    races); falls back to the meeting_cars defaults for lanes not yet seen.
    Returns a single dict with the primary mapping layered over the fallback.
    """
    session_ids = [s.id for s in dbsession.exec(
        select(RaceSession).where(RaceSession.meeting_id == meeting_id)
    ).all()]
    last_race = dbsession.exec(
        select(Race)
        .where(Race.session_id.in_(session_ids), Race.state == 'Finished')
        .order_by(Race.id.desc())
    ).first()
    last_race_lane_to_car = {}
    if last_race:
        last_driver_races = dbsession.exec(
            select(DriverRace).where(DriverRace.race_id == last_race.id)
        ).all()
        last_race_lane_to_car = {
            dr.lane: dr.car_id for dr in last_driver_races if dr.car_id is not None
        }

    meeting_cars = dbsession.exec(
        select(MeetingCar).where(MeetingCar.meeting_id == meeting_id)
    ).all()
    meeting_lane_to_car = {mc.lane: mc.car_id for mc in meeting_cars if mc.lane is not None}

    # Last-race assignment wins over the meeting default.
    return {**meeting_lane_to_car, **last_race_lane_to_car}


def _persist_race(dbsession, setup, race_session, race_number, lane_to_car):
    """Persist one NextRaceSetup as a NotStarted Race + DriverRace rows. No commit of
    the surrounding transaction beyond what's needed to obtain the race id."""
    race = Race(state='NotStarted', session_id=race_session.id, race_number=race_number)
    dbsession.add(race)
    dbsession.commit()
    dbsession.refresh(race)
    for lane_assignment in setup.lane_assignments:
        if lane_assignment.id == 0:
            continue
        dbsession.add(DriverRace(
            driver_id=lane_assignment.id,
            race_id=race.id,
            car_id=lane_to_car.get(lane_assignment.lane_number),
            lane=lane_assignment.lane_number,
        ))
    dbsession.commit()
    return race


def _next_race_number(dbsession, session_id):
    """The race_number for the next race appended to a session's queue: one past the
    count of existing races (finished, running, or already queued). Counting rather
    than max() keeps numbering correct even when older rows have a NULL race_number."""
    existing = dbsession.exec(
        select(Race).where(Race.session_id == session_id)
    ).all()
    return len(existing) + 1


def save_pending_race(dbsession, setup, race_session):
    """Persist a freshly calculated lineup as a NotStarted Race + DriverRace records."""
    lane_to_car = _lane_to_car_map(dbsession, race_session.meeting_id)
    _persist_race(dbsession, setup, race_session,
                  _next_race_number(dbsession, race_session.id), lane_to_car)
    # Reload from DB so the response includes everything load_pending_race adds
    # (car pictures, meeting display names), not just the in-memory lineup.
    return load_pending_race(dbsession)


def remove_pending_races(dbsession, session_id):
    """Delete every NotStarted race (and its lineup) for a session — the whole queue.

    Used when a session ends (no dangling pending race may survive a Finished session)
    and when regenerating the schedule after the driver roster changes.
    """
    pending = dbsession.exec(
        select(Race).where(Race.session_id == session_id, Race.state == 'NotStarted')
    ).all()
    for race in pending:
        for dr in dbsession.exec(
            select(DriverRace).where(DriverRace.race_id == race.id)
        ).all():
            dbsession.delete(dr)
        # Withdrawals only count once their race has run (Finished). A NotStarted race
        # being discarded never ran, so its withdrawals must not survive as phantom skips.
        for w in dbsession.exec(
            select(RaceWithdrawal).where(RaceWithdrawal.race_id == race.id)
        ).all():
            dbsession.delete(w)
        dbsession.delete(race)
    if pending:
        dbsession.commit()
    return len(pending)


def build_session_schedule(race_session, drivers, lanes):
    """Compute the full *remaining* race schedule for a session as a list of
    NextRaceSetup, one per race, in running order.

    Iterates the single-race balancer (select_balanced_race_drivers +
    assign_drivers_to_lanes) over in-memory copies of the driver stats — incrementing
    each chosen driver's completed_races and lane counts after every race — so the
    whole schedule balances exactly as the lazy one-at-a-time path did: every active
    driver ends on `races_per_driver` races, lanes are spread evenly, and the final
    races shrink rather than draining to a single straggler.

    `drivers` already reflects completed (Finished) races, so regenerating mid-session
    only schedules each driver's *outstanding* races. Sessions with no
    races_per_driver target return a single race (manual-end → stage one at a time).
    """
    work = [d.model_copy() for d in drivers]
    by_id = {d.id: d for d in work}

    if not race_session.races_per_driver:
        return [assign_drivers_to_lanes(work, lanes)]

    schedule = []
    # Defensive cap: at most one race per driver-target plus a margin.
    max_races = len(work) * race_session.races_per_driver + 1
    for _ in range(max_races):
        work.sort(key=lambda d: (d.sit_out_next_race, d.completed_races, d.random_value))
        selected, complete = select_balanced_race_drivers(race_session, work, lanes)
        if complete:
            break
        setup = assign_drivers_to_lanes(selected, lanes)
        schedule.append(setup)
        for la in setup.lane_assignments:
            if la.id == 0:
                continue
            d = by_id[la.id]
            d.completed_races += 1
            attr = f'lane{la.lane_number}_count'
            setattr(d, attr, getattr(d, attr) + 1)
    return schedule


def save_session_schedule(dbsession, schedule, race_session):
    """Persist a list of NextRaceSetup as consecutively-numbered NotStarted races,
    appended after any existing finished/running/queued races. Returns the count."""
    lane_to_car = _lane_to_car_map(dbsession, race_session.meeting_id)
    start_number = _next_race_number(dbsession, race_session.id)
    for offset, setup in enumerate(schedule):
        _persist_race(dbsession, setup, race_session, start_number + offset, lane_to_car)
    return len(schedule)
