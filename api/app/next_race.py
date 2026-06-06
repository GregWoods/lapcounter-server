import logging
import traceback
import random
from datetime import date as date_type
from typing import List
from fastapi import HTTPException
from sqlmodel import select
from model import *
from responsemodel import NextRaceSetup, DriverWithLane, RaceSessionWithState
from pprint import pprint


logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)


def get_drivers_for_next_race_sql(session):
    try:
        #if testing:
        #    seed_query = text("SELECT setseed(0.42)")
        #    session.exec(seed_query)

        from sqlalchemy import text
        query = text("""
            SELECT 
                d.id,
                --d.first_name, 
                --d.last_name,
                md.driver_name,
                d.sit_out_next_race,
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
            --LEFT_JOIN sessions s on md.meeting_id = s.meeting_id
            --LEFT JOIN meetings m ON s.meeting_id = m.id
            LEFT JOIN 
                driver_races dr ON d.id = dr.driver_id
            LEFT JOIN 
                races r ON dr.race_id = r.id AND r.state = 'Finished'
            GROUP BY 
                d.id, md.driver_name, d.sit_out_next_race
            ORDER BY 
                sit_out_next_race ASC, 
                completed_races ASC,
                random_value ASC
        """)
        rows = session.exec(query).all()
        # Convert SQL rows to DriverWithLane objects
        drivers = []
        for row in rows:
            driver = DriverWithLane(
                id=row.id,
                driver_name=row.driver_name,
                sit_out_next_race=row.sit_out_next_race,
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

    # Get all drivers who aren't sitting out
    available_racing_drivers = [d for d in available_drivers if not d.sit_out_next_race]
    
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


def get_active_meeting(session):
    """Return the earliest meeting with date >= today. Raises 404 if none found."""
    today = date_type.today()
    meeting = session.exec(
        select(Meeting).where(Meeting.date >= today).order_by(Meeting.date.asc())
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="No active or upcoming meetings found")
    return meeting


def get_active_meeting_id(session):
    return get_active_meeting(session).id


def get_active_session(session):
    """Return the active session for the active meeting.

    'Active' = earliest session in the active meeting that has no races yet,
    or has at least one non-Finished race. Falls back to the last session if
    all sessions are fully finished.
    """
    from sqlalchemy import text
    meeting_id = get_active_meeting_id(session)

    sessions = session.exec(
        select(RaceSession)
        .where(RaceSession.meeting_id == meeting_id)
        .order_by(RaceSession.id.asc())
    ).all()

    if not sessions:
        raise HTTPException(status_code=404, detail="No sessions found for active meeting")

    for s in sessions:
        races = session.exec(select(Race).where(Race.session_id == s.id)).all()
        if not races:
            return s  # pre-configured session with no races yet
        if any(r.state != 'Finished' for r in races):
            return s  # session still in progress

    return sessions[-1]  # all sessions finished — return last


def compute_session_state(races) -> str:
    if not races:
        return 'NotStarted'
    if all(r.state == 'Finished' for r in races):
        return 'Finished'
    if all(r.state == 'NotStarted' for r in races):
        return 'NotStarted'
    return 'InProgress'


def session_with_state(race_session, db_session) -> RaceSessionWithState:
    races = db_session.exec(select(Race).where(Race.session_id == race_session.id)).all()
    return RaceSessionWithState(
        **race_session.model_dump(),
        state=compute_session_state(races)
    )


def load_pending_race(session):
    """Load the existing NotStarted race from DB. Returns NextRaceSetup or None."""
    pending_race = session.exec(select(Race).where(Race.state == 'NotStarted')).first()
    if not pending_race:
        return None

    driver_races = session.exec(
        select(DriverRace).where(DriverRace.race_id == pending_race.id)
    ).all()

    # Stale race with no lineup (e.g. from sample data) — delete and recalculate
    if not driver_races:
        session.delete(pending_race)
        session.commit()
        return None

    lanes_list = session.exec(select(Lane).order_by(Lane.lane_number)).all()

    assigned_driver_ids = {dr.driver_id for dr in driver_races}
    driver_race_by_lane = {dr.lane: dr for dr in driver_races}

    # Map car_id → picture for the cars assigned to this race's lanes
    car_ids = {dr.car_id for dr in driver_races if dr.car_id is not None}
    car_pictures = {}
    if car_ids:
        car_rows = session.exec(select(Car).where(Car.id.in_(car_ids))).all()
        car_pictures = {c.id: c.picture for c in car_rows}

    # Reuse existing SQL for driver stats (lane counts, completed_races, etc.)
    all_drivers = get_drivers_for_next_race_sql(session)
    all_drivers_map = {d.id: d for d in all_drivers}

    # Get meeting-specific display names
    race_session = session.get(RaceSession, pending_race.session_id)
    md_rows = session.exec(
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

    return NextRaceSetup(
        race_id=pending_race.id,
        lane_assignments=lane_assignments,
        other_drivers=other_drivers,
    )


def set_lane_enabled(session, lane_number: int, enabled: bool):
    """Enable or disable a lane and update the pending race lineup accordingly."""
    lane = session.get(Lane, lane_number)
    if not lane:
        raise HTTPException(status_code=404, detail="Lane not found")

    lane.enabled = enabled
    session.add(lane)
    session.commit()

    pending_race = session.exec(select(Race).where(Race.state == 'NotStarted')).first()
    if not pending_race:
        return load_pending_race(session)

    if not enabled:
        driver_race = session.exec(
            select(DriverRace).where(
                DriverRace.race_id == pending_race.id,
                DriverRace.lane == lane_number
            )
        ).first()
        if driver_race:
            session.delete(driver_race)
            session.commit()
    else:
        existing = session.exec(
            select(DriverRace).where(DriverRace.race_id == pending_race.id)
        ).all()
        assigned_ids = {dr.driver_id for dr in existing}

        all_drivers = get_drivers_for_next_race_sql(session)
        next_driver = next(
            (d for d in all_drivers if not d.sit_out_next_race and d.id not in assigned_ids),
            None
        )

        if next_driver:
            race_session = session.get(RaceSession, pending_race.session_id)
            meeting_car = session.exec(
                select(MeetingCar).where(
                    MeetingCar.meeting_id == race_session.meeting_id,
                    MeetingCar.lane == lane_number
                )
            ).first()
            session.add(DriverRace(
                driver_id=next_driver.id,
                race_id=pending_race.id,
                car_id=meeting_car.car_id if meeting_car else None,
                lane=lane_number,
            ))
            session.commit()

    return load_pending_race(session)


def save_pending_race(session, setup, meeting_id):
    """Persist a freshly calculated lineup as a NotStarted Race + DriverRace records."""
    # Find or create a session for this meeting
    race_session = session.exec(
        select(RaceSession).where(RaceSession.meeting_id == meeting_id)
    ).first()
    if not race_session:
        race_session = RaceSession(
            meeting_id=meeting_id,
            session_type='Points',
            end_condition='Laps',
            scoring_method='PositionPoints',
        )
        session.add(race_session)
        session.commit()
        session.refresh(race_session)

    race = Race(state='NotStarted', session_id=race_session.id)
    session.add(race)
    session.commit()
    session.refresh(race)

    # Primary: lane → car_id from the last completed race in this meeting
    session_ids = [s.id for s in session.exec(
        select(RaceSession).where(RaceSession.meeting_id == meeting_id)
    ).all()]
    last_race = session.exec(
        select(Race)
        .where(Race.session_id.in_(session_ids), Race.state == 'Finished')
        .order_by(Race.id.desc())
    ).first()
    last_race_lane_to_car = {}
    if last_race:
        last_driver_races = session.exec(
            select(DriverRace).where(DriverRace.race_id == last_race.id)
        ).all()
        last_race_lane_to_car = {
            dr.lane: dr.car_id for dr in last_driver_races if dr.car_id is not None
        }

    # Fallback: lane → car_id from meeting_cars defaults
    meeting_cars = session.exec(
        select(MeetingCar).where(MeetingCar.meeting_id == meeting_id)
    ).all()
    meeting_lane_to_car = {mc.lane: mc.car_id for mc in meeting_cars if mc.lane is not None}

    for lane_assignment in setup.lane_assignments:
        if lane_assignment.id == 0:
            continue
        car_id = last_race_lane_to_car.get(lane_assignment.lane_number) or meeting_lane_to_car.get(lane_assignment.lane_number)
        driver_race = DriverRace(
            driver_id=lane_assignment.id,
            race_id=race.id,
            car_id=car_id,
            lane=lane_assignment.lane_number,
        )
        session.add(driver_race)

    session.commit()
    # Reload from DB so the response includes everything load_pending_race adds
    # (car pictures, meeting display names), not just the in-memory lineup.
    return load_pending_race(session)
