import os
import subprocess
import time as time_module
import logging
import traceback
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Annotated, Optional
from datetime import datetime, timezone
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from settings import Settings
from model import *
from responsemodel import RaceSessionWithState, RaceSessionSummary
from next_race import get_drivers_for_next_race_sql, assign_drivers_to_lanes, load_pending_race, load_current_race, save_pending_race, find_pending_race, get_active_meeting, get_active_meeting_id, get_active_session, get_session_for_results, session_with_state, set_lane_enabled, add_driver_to_pending_lineup, recalculate_meeting_driver_names, select_balanced_race_drivers, compute_session_progress, load_race_queue, remove_pending_races, build_session_schedule, save_session_schedule, record_withdrawal, clear_withdrawal, session_skip_counts, set_driver_disqualified, clear_session_withdrawals
from points import calculate_race_points

settings = Settings()

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

#asyncio_engine = create_async_engine(
#engine = create_engine(f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}")
#    connect_args={"check_same_thread": False},
#    echo=True)
try:
    connection_string = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
    print(f"Connection string: {connection_string}")
    engine = create_engine(connection_string)
except Exception as e:
    print(f"Error creating engine: {e}")
    raise



def get_session():
    with Session(engine) as dbsession:
        yield dbsession

SessionDep = Annotated[Session, Depends(get_session)]

app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(f"Unhandled exception: {error_detail}")
    return JSONResponse(
        status_code=500,
        content={"message": str(exc), "detail": error_detail},
    )

app.mount("/media", StaticFiles(directory=settings.MEDIA_FOLDER), name="media")

cors_origins = [
    settings.REACT_URL,
    "http://localhost:5173",    # when using the development vite server not in docker
    "http://localhost:8088"     # when using the development vite server using docker compose
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/cars")
def get_cars(dbsession: SessionDep):
    car_pic_base_url = f"{settings.API_URL}/{settings.CARS_MEDIA_FOLDER}"
    cars = dbsession.exec(select(Car)).all()
    return [
        {"id": c.id, "name": c.name, "picture": c.picture, "url": f"{car_pic_base_url}/{c.picture}"}
        for c in cars if c.picture
    ]


@app.get("/meetings")
def get_all_meetings(dbsession: SessionDep):
    try:
        meetings = dbsession.exec(select(Meeting)).all()
        return meetings
    except Exception as e:
        logger.error(f"Error retrieving meetings: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = { "message": str(e), "traceback": traceback.format_exc(), "model": str(Meeting.__dict__) }
        raise HTTPException(status_code=500, detail=error_detail)

@app.get("/meetings/active", response_model=Meeting)
def get_active_meeting_endpoint(dbsession: SessionDep):
    return get_active_meeting(dbsession)


@app.get("/meetings/upcoming")
def get_upcoming_meetings(dbsession: SessionDep):
    try:
        meetings = dbsession.exec(select(Meeting).where(Meeting.date >= date.today())).all()
        return meetings
    except Exception as e:
        logger.error(f"Error retrieving meetings: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = { "message": str(e), "traceback": traceback.format_exc(), "model": str(Meeting.__dict__) }
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/meetings/", response_model=Meeting)
def create_meeting(meeting: MeetingCreate, dbsession: SessionDep) -> Meeting:
    db_meeting = Meeting(**meeting.model_dump())
    dbsession.add(db_meeting)
    dbsession.commit()
    dbsession.refresh(db_meeting)
    return db_meeting


@app.patch("/meetings/{meeting_id}", response_model=Meeting)
def update_meeting(meeting_id: int, update: MeetingUpdate, dbsession: SessionDep) -> Meeting:
    meeting = dbsession.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(meeting, field, value)
    dbsession.add(meeting)
    dbsession.commit()
    dbsession.refresh(meeting)
    return meeting


@app.get("/sessions",
         summary="Get race sessions",
         description="Retrieve all race sessions, or filter by meeting ID",
         response_model=list[RaceSessionSummary])
def get_sessions_by_meeting_id(
    dbsession: SessionDep,
    meeting_id: int = Query(None,
        description="Filter sessions by meeting ID",
    )
):
    try:
        query = select(RaceSession).order_by(RaceSession.id)
        if meeting_id is not None:
            query = query.where(RaceSession.meeting_id == meeting_id)
        race_sessions = dbsession.exec(query).all()
        result = []
        for s in race_sessions:
            races_total = None
            if s.races_per_driver:
                all_drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=s.id)
                _done, races_total = compute_session_progress(s, all_drivers, dbsession)
            result.append(RaceSessionSummary(**s.model_dump(), races_total=races_total))
        return result
    except Exception as e:
        logger.error(f"Error retrieving sessions: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = { "message": str(e), "traceback": traceback.format_exc(), "model": str(RaceSession.__dict__) }
        raise HTTPException(status_code=500, detail=error_detail)


def get_lanes(dbsession: SessionDep):
    try:
        lanes = dbsession.exec(select(Lane).order_by(Lane.lane_number)).all()
        return lanes
    except Exception as e:
        logger.error(f"Error retrieving lanes: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)
    

@app.post("/sessions/", response_model=RaceSession)
def create_session(session: RaceSessionCreate, dbsession: SessionDep) -> RaceSession:
    db_session = RaceSession(**session.model_dump())
    dbsession.add(db_session)
    dbsession.commit()
    dbsession.refresh(db_session)
    return db_session


@app.get("/sessions/active", response_model=RaceSessionWithState)
def get_active_session_endpoint(dbsession: SessionDep):
    return session_with_state(get_active_session(dbsession), dbsession)


@app.get("/sessions/{session_id}", response_model=RaceSessionWithState)
def get_session(session_id: int, dbsession: SessionDep):
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_with_state(race_session, dbsession)


@app.patch("/sessions/{session_id}", response_model=RaceSession)
def update_session(session_id: int, session_update: RaceSessionUpdate, dbsession: SessionDep):
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    update_data = session_update.model_dump(exclude_unset=True)
    race_session.sqlmodel_update(update_data)
    dbsession.add(race_session)
    dbsession.commit()
    dbsession.refresh(race_session)
    return race_session


@app.get("/races/current/")
def get_current_race(dbsession: SessionDep):
    """The race the UI should show now: the Running race if one exists, else the next
    queued (NotStarted) race. Read-only — the DB is authoritative for *which* race is
    current; lapdata's race_state is a live overlay applied only when race_ids match.
    Returns 404 when no session is in progress (nothing to show until one is started).
    """
    current = load_current_race(dbsession)
    if current:
        return current
    pending = load_pending_race(dbsession)
    if pending:
        return pending
    raise HTTPException(status_code=404, detail="No current race — no session in progress")


@app.get("/races/pending/")
def get_pending_race(dbsession: SessionDep):
    """Read-only: the next race to run (head of the session's queue), or 404 if none.

    Races are no longer created on read — the whole session is pre-populated when it
    is started (POST /sessions/start-next) and topped up by regeneration. A 404 here
    means there is no in-progress session with a queued race (e.g. between sessions),
    not that one should be conjured.
    """
    existing = load_pending_race(dbsession)
    if existing:
        return existing
    raise HTTPException(status_code=404, detail="No pending race — start a session first")


@app.get("/races/queue/")
def get_race_queue(dbsession: SessionDep):
    """Read-only: the ordered list of upcoming (NotStarted) races for the active
    session. The head is the next race; the tail is the lookahead the NextRace page
    previews. Empty list when no session is in progress."""
    return load_race_queue(dbsession)


def generate_session_schedule(dbsession: SessionDep, race_session):
    """Pre-populate (or top up) a session's race queue: compute the full balanced
    schedule for every outstanding race and persist them as NotStarted races. Assumes
    any stale queue has already been cleared. Returns the number of races created."""
    lanes = get_lanes(dbsession)
    drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=race_session.id)
    schedule = build_session_schedule(race_session, drivers, lanes)
    return save_session_schedule(dbsession, schedule, race_session)


@app.post("/sessions/start-next")
def start_next_session(dbsession: SessionDep):
    """Operator action ("Next Session"): begin the next NotStarted session in the
    active meeting and pre-populate its full race queue. Ending is automatic; starting
    a session is always this manual step (directive: no race exists until a session is
    started). 409 if a session is already in progress, 404 if none is queued."""
    meeting_id = get_active_meeting_id(dbsession)
    in_progress = dbsession.exec(
        select(RaceSession)
        .where(RaceSession.meeting_id == meeting_id, RaceSession.state == 'InProgress')
    ).first()
    if in_progress:
        raise HTTPException(status_code=409, detail="A session is already in progress")
    nxt = dbsession.exec(
        select(RaceSession)
        .where(RaceSession.meeting_id == meeting_id, RaceSession.state == 'NotStarted')
        .order_by(RaceSession.id)
    ).first()
    if not nxt:
        raise HTTPException(status_code=404, detail="No upcoming session to start")
    nxt.state = 'InProgress'
    dbsession.add(nxt)
    dbsession.commit()
    count = generate_session_schedule(dbsession, nxt)
    return {"session_id": nxt.id, "races_generated": count}


@app.get("/sessions/active/regen-status")
def session_regen_status(dbsession: SessionDep):
    """Whether the active session's upcoming queue is stale — i.e. an eligible driver
    (still under the race target, not sitting out) appears in no upcoming race. That
    only happens when the roster changed after the schedule was built (a late arrival),
    so it drives the RaceControl "New driver added, regenerate?" prompt. Returns
    needs_regeneration=False for manual-end sessions (no fixed schedule to be stale)."""
    quiet = {"needs_regeneration": False, "missing_driver_names": [], "session_id": None,
             "sit_out_candidates": []}
    try:
        session = get_active_session(dbsession)
    except HTTPException:
        return quiet
    if session.state != 'InProgress':
        return quiet

    drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=session.id)

    # Drivers who have sat out too many races and could be disqualified from the rest of
    # the session. Only offered when the session sets a max_sit_outs limit; already-DQ'd
    # drivers are excluded. Cumulative skips = withdrawals on the session's finished races.
    sit_out_candidates = []
    if session.max_sit_outs:
        skips = session_skip_counts(dbsession, session.id)
        sit_out_candidates = [
            {"driver_id": d.id, "driver_name": d.driver_name, "sit_outs": skips[d.id]}
            for d in drivers
            if not d.disqualified and skips.get(d.id, 0) >= session.max_sit_outs
        ]

    if not session.races_per_driver:
        return {**quiet, "session_id": session.id, "sit_out_candidates": sit_out_candidates}

    target = session.races_per_driver
    queued_race_ids = [r.id for r in dbsession.exec(
        select(Race).where(Race.session_id == session.id, Race.state == 'NotStarted')
    ).all()]
    queued_driver_ids = set()
    if queued_race_ids:
        for dr in dbsession.exec(
            select(DriverRace).where(DriverRace.race_id.in_(queued_race_ids))
        ).all():
            queued_driver_ids.add(dr.driver_id)
    missing = [d for d in drivers
               if not d.sit_out_next_race
               and not d.disqualified
               and d.completed_races < target
               and d.id not in queued_driver_ids]
    return {
        "session_id": session.id,
        "needs_regeneration": len(missing) > 0,
        "missing_driver_names": [d.driver_name for d in missing],
        "sit_out_candidates": sit_out_candidates,
    }


@app.post("/sessions/{session_id}/regenerate-races")
def regenerate_session_races(session_id: int, dbsession: SessionDep):
    """Rebuild the queue of upcoming races for an in-progress session — used after the
    driver roster changes mid-session (e.g. a late arrival is added). Finished/running
    races are untouched; the NotStarted queue is discarded and recomputed from each
    driver's *outstanding* race count. 409 unless the session is in progress."""
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if race_session.state != 'InProgress':
        raise HTTPException(status_code=409, detail="Can only regenerate races for an in-progress session")
    remove_pending_races(dbsession, session_id)
    count = generate_session_schedule(dbsession, race_session)
    return {"races_generated": count}


@app.post("/sessions/{session_id}/drivers/{driver_id}/disqualify")
def disqualify_driver(session_id: int, driver_id: int, dbsession: SessionDep):
    """Remove a driver from the rest of a session (they've sat out too many races). Sets
    the per-session disqualified flag and rebuilds the upcoming queue so the remaining
    races refill without them. 409 unless the session is in progress."""
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if race_session.state != 'InProgress':
        raise HTTPException(status_code=409, detail="Can only disqualify from an in-progress session")
    set_driver_disqualified(dbsession, session_id, driver_id, True)
    remove_pending_races(dbsession, session_id)
    count = generate_session_schedule(dbsession, race_session)
    return {"races_generated": count}


@app.post("/sessions/{session_id}/drivers/{driver_id}/reinstate")
def reinstate_driver(session_id: int, driver_id: int, dbsession: SessionDep):
    """Undo a disqualification and rebuild the upcoming queue so the driver is scheduled
    again for their outstanding races. 409 unless the session is in progress."""
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if race_session.state != 'InProgress':
        raise HTTPException(status_code=409, detail="Can only reinstate for an in-progress session")
    set_driver_disqualified(dbsession, session_id, driver_id, False)
    # A deliberate reinstate forgives past sit-outs, else the disqualify prompt fires again.
    clear_session_withdrawals(dbsession, session_id, driver_id)
    remove_pending_races(dbsession, session_id)
    count = generate_session_schedule(dbsession, race_session)
    return {"races_generated": count}


@app.post("/races/{race_id}/start")
def start_race(
    race_id: int, dbsession: SessionDep,
    started_at: Optional[float] = Body(default=None, embed=True),
):
    """started_at is the lights-out unix timestamp from lapdata's authoritative
    race_start_time — more precise than server time here, since this is a
    fire-and-forget POST from a background thread, not called at the go instant."""
    race = dbsession.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    race.state = 'Running'
    if started_at is not None:
        race.started_at = datetime.fromtimestamp(started_at, tz=timezone.utc)
    dbsession.add(race)
    session = dbsession.get(RaceSession, race.session_id)
    if session and session.state == 'NotStarted':
        session.state = 'InProgress'
        dbsession.add(session)
    dbsession.commit()
    return {"ok": True}


@app.post("/races/{race_id}/finish")
def finish_race(race_id: int, dbsession: SessionDep):
    race = dbsession.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    race.state = 'Finished'
    dbsession.add(race)
    dbsession.commit()
    session = dbsession.get(RaceSession, race.session_id)
    if session and session.races_per_driver:
        target = session.races_per_driver
        if target:
            all_drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=session.id)
            eligible = [d for d in all_drivers
                        if not d.sit_out_next_race and not d.disqualified and d.completed_races < target]
            if not eligible:
                # Auto-end the session (ending is automatic). Starting the NEXT
                # session is a manual operator action from /racecontrol — it begins
                # when the first race of that session is started — so we do NOT
                # promote it here.
                session.state = 'Finished'
                dbsession.add(session)
                dbsession.commit()
                # No NotStarted race may outlive a Finished session.
                remove_pending_races(dbsession, session.id)
    return {"ok": True}


@app.get("/drivers/nextrace/")
def get_drivers_for_next_race(dbsession: SessionDep):
    active_session = get_active_session(dbsession)
    lanes = get_lanes(dbsession)
    drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=active_session.id)
    return assign_drivers_to_lanes(drivers, lanes)



@app.post("/drivers/")
def create_driver(driver: Driver, dbsession: SessionDep) -> Driver:
    dbsession.add(driver)
    dbsession.commit()
    dbsession.refresh(driver)
    return driver

@app.get("/drivers/")
def get_all_drivers(
    dbsession: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
) -> list[Driver]:
    drivers = dbsession.exec(select(Driver).offset(offset).limit(limit)).all()
    return drivers

@app.get("/drivers/search")
def search_drivers(q: str, dbsession: SessionDep) -> list[Driver]:
    """Case-insensitive first-name search for the self-registration flow."""
    return dbsession.exec(
        select(Driver).where(Driver.first_name.ilike(q))
    ).all()

@app.get("/drivers/{driver_id}/meetings")
def get_driver_meeting_ids(driver_id: int, dbsession: SessionDep) -> list[int]:
    """Return the meeting IDs the driver is registered for."""
    rows = dbsession.exec(
        select(MeetingDriver.meeting_id).where(MeetingDriver.driver_id == driver_id)
    ).all()
    return list(rows)

@app.get("/drivers/{driver_id}")
def get_driver(driver_id: int, dbsession: SessionDep) -> Driver:
    driver = dbsession.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver

@app.patch("/drivers/{driver_id}")
def update_driver(driver_id: int, body: dict, dbsession: SessionDep) -> Driver:
    driver = dbsession.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    for field in ("first_name", "last_name", "sit_out_next_race"):
        if field in body:
            setattr(driver, field, body[field])
    dbsession.add(driver)
    dbsession.commit()
    dbsession.refresh(driver)
    return driver

@app.delete("/drivers/{driver_id}")
def delete_driver(driver_id: int, dbsession: SessionDep):
    driver = dbsession.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    dbsession.delete(driver)
    dbsession.commit()
    return {"ok": True}


@app.post("/meetings/{meeting_id}/drivers")
def add_driver_to_meeting(meeting_id: int, body: PendingRaceAddDriver, dbsession: SessionDep):
    """Register a driver for a meeting and recompute all display names."""
    meeting = dbsession.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    driver = dbsession.get(Driver, body.driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    existing = dbsession.exec(
        select(MeetingDriver).where(
            MeetingDriver.meeting_id == meeting_id,
            MeetingDriver.driver_id == body.driver_id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Driver already registered for this meeting")

    dbsession.add(MeetingDriver(
        meeting_id=meeting_id,
        driver_id=body.driver_id,
        driver_name=driver.first_name,  # recalculated below
    ))
    dbsession.commit()
    recalculate_meeting_driver_names(dbsession, meeting_id)
    return {"ok": True}




@app.patch("/lanes/{lane_number}")
def patch_lane(lane_number: int, update: LaneUpdate, dbsession: SessionDep):
    return set_lane_enabled(dbsession, lane_number, update.enabled)


@app.delete("/races/pending/lanes/{lane_number}")
def remove_driver_from_pending_lane(lane_number: int, dbsession: SessionDep):
    pending_race = find_pending_race(dbsession)
    if not pending_race:
        raise HTTPException(status_code=404, detail="No pending race")
    driver_race = dbsession.exec(
        select(DriverRace).where(
            DriverRace.race_id == pending_race.id,
            DriverRace.lane == lane_number
        )
    ).first()
    if driver_race:
        driver_id = driver_race.driver_id
        dbsession.delete(driver_race)
        dbsession.commit()
        # Removing a scheduled driver is an operator withdrawal: if this race runs
        # without them it counts as a skip toward the session sit-out limit.
        record_withdrawal(dbsession, pending_race.id, driver_id)
    return load_pending_race(dbsession)


@app.post("/races/pending/drivers")
def add_driver_to_pending_race(body: PendingRaceAddDriver, dbsession: SessionDep):
    pending_race = find_pending_race(dbsession)
    if not pending_race:
        raise HTTPException(status_code=404, detail="No pending race")
    return add_driver_to_pending_lineup(dbsession, pending_race, body.driver_id)


@app.patch("/races/pending/lanes/{lane_number}")
def update_pending_race_lane_car(lane_number: int, update: LaneCarUpdate, dbsession: SessionDep):
    pending_race = find_pending_race(dbsession)
    if not pending_race:
        raise HTTPException(status_code=404, detail="No pending race")
    driver_race = dbsession.exec(
        select(DriverRace).where(
            DriverRace.race_id == pending_race.id,
            DriverRace.lane == lane_number
        )
    ).first()
    if not driver_race:
        raise HTTPException(status_code=404, detail="No driver assigned to that lane")
    driver_race.car_id = update.car_id
    dbsession.add(driver_race)
    dbsession.commit()
    return load_pending_race(dbsession)


@app.patch("/races/{race_id}/lanes/{lane_number}")
def update_race_lane_car(race_id: int, lane_number: int, update: LaneCarUpdate, dbsession: SessionDep):
    driver_race = dbsession.exec(
        select(DriverRace).where(
            DriverRace.race_id == race_id,
            DriverRace.lane == lane_number
        )
    ).first()
    if not driver_race:
        raise HTTPException(status_code=404, detail="No driver assigned to that lane")
    driver_race.car_id = update.car_id
    dbsession.add(driver_race)
    dbsession.commit()
    return {"ok": True}


@app.post("/sessions/{session_id}/finish")
def finish_session(session_id: int, dbsession: SessionDep):
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    race_session.state = 'Finished'
    dbsession.add(race_session)
    # Next session is started manually from /racecontrol (Next Session → start-next),
    # not auto-promoted here.
    dbsession.commit()
    # No NotStarted race may outlive a Finished session — drop the whole queue.
    remove_pending_races(dbsession, race_session.id)
    return {"ok": True}



def build_session_results(race_session, dbsession):
    from collections import defaultdict
    meeting = dbsession.get(Meeting, race_session.meeting_id)
    meeting_name = meeting.name if meeting else ""
    sibling_sessions = dbsession.exec(
        select(RaceSession)
        .where(RaceSession.meeting_id == race_session.meeting_id)
        .order_by(RaceSession.id)
    ).all()
    sessions_list = [{"id": s.id, "session_type": s.session_type, "state": s.state} for s in sibling_sessions]
    empty = {"session_id": race_session.id, "session_type": race_session.session_type,
             "meeting_name": meeting_name, "scoring_method": race_session.scoring_method,
             "races": [], "drivers": [], "sessions": sessions_list}

    races = dbsession.exec(
        select(Race)
        .where(Race.session_id == race_session.id, Race.state == 'Finished')
        .order_by(Race.id)
    ).all()
    if not races:
        return empty

    race_ids = [r.id for r in races]
    all_driver_races = dbsession.exec(
        select(DriverRace).where(DriverRace.race_id.in_(race_ids))
    ).all()

    races_with_data = {dr.race_id for dr in all_driver_races}
    races = [r for r in races if r.id in races_with_data]
    race_ids = [r.id for r in races]
    if not races:
        return empty

    md_rows = dbsession.exec(
        select(MeetingDriver).where(MeetingDriver.meeting_id == race_session.meeting_id)
    ).all()
    meeting_driver_names = {md.driver_id: md.driver_name for md in md_rows}

    race_groups = defaultdict(list)
    for dr in all_driver_races:
        race_groups[dr.race_id].append(dr)

    scoring_method = race_session.scoring_method
    races_out = [{"race_id": r.id, "race_number": r.race_number or (i + 1)} for i, r in enumerate(races)]

    if race_session.session_type == 'FastestLap':
        all_dr_ids = [dr.id for dr in all_driver_races]
        all_laps = dbsession.exec(
            select(DriverLap).where(DriverLap.driver_race_id.in_(all_dr_ids))
        ).all()

        best_lap_per_dr: dict = {}
        for lap in all_laps:
            t = float(lap.lap_time)
            prev = best_lap_per_dr.get(lap.driver_race_id)
            if prev is None or t < prev:
                best_lap_per_dr[lap.driver_race_id] = t

        best_lap_by_race: dict = defaultdict(dict)
        for dr in all_driver_races:
            best = best_lap_per_dr.get(dr.id)
            if best is not None:
                best_lap_by_race[dr.race_id][dr.driver_id] = best

        driver_rows = []
        for did, name in meeting_driver_names.items():
            laptimes_map = {str(race_id): best_lap_by_race.get(race_id, {}).get(did) for race_id in race_ids}
            valid_times = [t for t in laptimes_map.values() if t is not None]
            best_lap = round(min(valid_times), 3) if valid_times else None
            avg_lap = round(sum(valid_times) / len(valid_times), 3) if valid_times else None
            summary = avg_lap if scoring_method == 'AverageFastestLap' else best_lap
            driver_rows.append({
                "driver_id": did, "driver_name": name,
                "lap_times": laptimes_map,
                "best_lap": best_lap,
                "avg_best_lap": avg_lap,
                "total_lap_time": summary,
                "races_entered": len(valid_times),
            })

        driver_rows.sort(key=lambda d: (d["total_lap_time"] is None, d["total_lap_time"] or 0))

        return {
            "session_id": race_session.id,
            "session_type": race_session.session_type,
            "meeting_name": meeting_name,
            "scoring_method": scoring_method,
            "races": races_out,
            "drivers": driver_rows,
            "sessions": sessions_list,
        }

    # Points / position scoring path
    scoring_points_json = race_session.scoring_points
    positions = {}
    laps_by_race = defaultdict(dict)
    for race_id in race_ids:
        sorted_drs = sorted(
            race_groups.get(race_id, []),
            key=lambda dr: (-(dr.laps_completed or 0), dr.fastest_lap_time or 999999)
        )
        positions[race_id] = {dr.driver_id: i + 1 for i, dr in enumerate(sorted_drs)}
        for dr in race_groups.get(race_id, []):
            laps_by_race[race_id][dr.driver_id] = dr.laps_completed

    driver_rows = []
    for did, name in meeting_driver_names.items():
        pos_map = {str(race_id): positions.get(race_id, {}).get(did) for race_id in race_ids}
        pts_map = {
            str(race_id): calculate_race_points(
                scoring_method, scoring_points_json,
                positions.get(race_id, {}).get(did),
                laps_by_race.get(race_id, {}).get(did),
            )
            for race_id in race_ids
        }
        races_entered = sum(1 for p in pos_map.values() if p is not None)
        driver_rows.append({
            "driver_id": did, "driver_name": name,
            "positions": pos_map, "points": pts_map,
            "total_points": sum(pts_map.values()), "races_entered": races_entered,
        })

    driver_rows.sort(key=lambda d: (-d["total_points"], d["races_entered"]))

    return {
        "session_id": race_session.id,
        "session_type": race_session.session_type,
        "meeting_name": meeting_name,
        "scoring_method": scoring_method,
        "races": races_out,
        "drivers": driver_rows,
        "sessions": sessions_list,
    }


@app.get("/sessions/current/results")
def get_current_session_results(dbsession: SessionDep):
    # "current" = active session if there is one, else the most recently finished
    # session (so results stay viewable after a meeting ends). Mirrors /races/current/.
    return build_session_results(get_session_for_results(dbsession), dbsession)


@app.get("/sessions/{session_id}/results")
def get_session_results(session_id: int, dbsession: SessionDep):
    race_session = dbsession.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    return build_session_results(race_session, dbsession)


# === Admin Utility Endpoints ===

@app.get("/admin/clock")
def get_clock():
    return {"timestamp": time_module.time()}


class SyncClockRequest(BaseModel):
    timestamp: float


@app.post("/admin/sync-clock")
def sync_clock(body: SyncClockRequest):
    ts = body.timestamp
    if not (1_000_000_000 < ts < 9_999_999_999):
        raise HTTPException(status_code=422, detail="timestamp out of plausible range")
    try:
        subprocess.run(["date", "-s", f"@{ts:.3f}"], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to set clock: {e.stderr.decode()}")
    return {"ok": True, "timestamp": time_module.time()}


# === Diagnostic Endpoints ===

@app.get("/verify-db")
def verify_db():
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return {"status": "connected", "tables": tables}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/import-check")
def import_check():
    import sys
    modules = [name for name in sys.modules if "model" in name.lower()]
    return {"modules": modules}    


@app.get("/minimal-debug")
def minimal_debug():
    import sys
    import inspect
    
    # Create a debug log file
    with open("debug_output.txt", "w") as f:
        # Write basic environment info
        f.write(f"Python version: {sys.version}\n")
        f.write(f"SQLModel version: {SQLModel.__version__ if hasattr(SQLModel, '__version__') else 'unknown'}\n")
        
        # List all models from model.py
        f.write("\nModels imported:\n")
        for name, obj in inspect.getmembers(sys.modules["model"]):
            if isinstance(obj, type) and issubclass(obj, SQLModel) and obj != SQLModel:
                f.write(f"- {name}: {obj}\n")
                
        # Try to access Meeting attributes
        f.write("\nMeeting inspection:\n")
        try:
            f.write(f"Meeting tablename: {Meeting.__tablename__}\n")
            f.write(f"Meeting fields: {Meeting.__fields__}\n")
        except Exception as e:
            f.write(f"Error inspecting Meeting: {e}\n")
    
    return {"message": "Debug info written to debug_output.txt"}


@app.get("/meetings-schema")
def get_meetings_schema():
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        
        # Get table schema
        columns = inspector.get_columns("meetings") if "meetings" in inspector.get_table_names() else []
        schema = {col["name"]: str(col["type"]) for col in columns}
        
        # Get model definition
        model_attrs = {
            attr: str(type(getattr(Meeting, attr)))
            for attr in dir(Meeting)
            if not attr.startswith("_") and attr != "metadata"
        }
        
        return {
            "table_exists": "meetings" in inspector.get_table_names(),
            "table_schema": schema,
            "model_definition": model_attrs
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

