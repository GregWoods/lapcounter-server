import os
import logging
import traceback
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from settings import Settings
from model import *
from responsemodel import RaceSessionWithState
from next_race import get_drivers_for_next_race_sql, assign_drivers_to_lanes, load_pending_race, save_pending_race, get_active_meeting, get_active_session, session_with_state, set_lane_enabled, add_driver_to_pending_lineup
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
        meetings = dbsession.exec(select(Meeting).where(Meeting.date >= datetime.now())).all()
        return meetings
    except Exception as e:
        logger.error(f"Error retrieving meetings: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = { "message": str(e), "traceback": traceback.format_exc(), "model": str(Meeting.__dict__) }
        raise HTTPException(status_code=500, detail=error_detail)


@app.get("/sessions", 
         summary="Get race sessions",
         description="Retrieve all race sessions, or filter by meeting ID",
         response_model=list[RaceSession])
def get_sessions_by_meeting_id(
    dbsession: SessionDep, 
    meeting_id: int = Query(None, 
        description="Filter sessions by meeting ID",
    )
):
    try:
        if meeting_id is not None:
            race_sessions = dbsession.exec(select(RaceSession).where(RaceSession.meeting_id == meeting_id)).all()
        else:
            race_sessions = dbsession.exec(select(RaceSession)).all()
        return race_sessions
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


@app.get("/races/pending/")
def get_pending_race(dbsession: SessionDep):
    existing = load_pending_race(dbsession)
    if existing:
        return existing
    active_session = get_active_session(dbsession)
    lanes = get_lanes(dbsession)
    drivers = get_drivers_for_next_race_sql(dbsession, race_session_id=active_session.id)
    setup = assign_drivers_to_lanes(drivers, lanes)
    return save_pending_race(dbsession, setup, active_session.meeting_id)


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

@app.get("/drivers/{driver_id}")
def get_driver(driver_id: int, dbsession: SessionDep) -> Driver:
    driver = dbsession.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver

@app.delete("/drivers/{driver_id}")
def delete_driver(driver_id: int, dbsession: SessionDep):
    driver = dbsession.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    dbsession.delete(driver)
    dbsession.commit()
    return {"ok": True}




@app.patch("/lanes/{lane_number}")
def patch_lane(lane_number: int, update: LaneUpdate, dbsession: SessionDep):
    return set_lane_enabled(dbsession, lane_number, update.enabled)


@app.delete("/races/pending/lanes/{lane_number}")
def remove_driver_from_pending_lane(lane_number: int, dbsession: SessionDep):
    pending_race = dbsession.exec(select(Race).where(Race.state == 'NotStarted')).first()
    if not pending_race:
        raise HTTPException(status_code=404, detail="No pending race")
    driver_race = dbsession.exec(
        select(DriverRace).where(
            DriverRace.race_id == pending_race.id,
            DriverRace.lane == lane_number
        )
    ).first()
    if driver_race:
        dbsession.delete(driver_race)
        dbsession.commit()
    return load_pending_race(dbsession)


@app.post("/races/pending/drivers")
def add_driver_to_pending_race(body: PendingRaceAddDriver, dbsession: SessionDep):
    pending_race = dbsession.exec(select(Race).where(Race.state == 'NotStarted')).first()
    if not pending_race:
        raise HTTPException(status_code=404, detail="No pending race")
    return add_driver_to_pending_lineup(dbsession, pending_race, body.driver_id)


@app.patch("/races/pending/lanes/{lane_number}")
def update_pending_race_lane_car(lane_number: int, update: LaneCarUpdate, dbsession: SessionDep):
    pending_race = dbsession.exec(select(Race).where(Race.state == 'NotStarted')).first()
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


@app.post("/races/{race_id}/start")
def start_race(race_id: int, dbsession: SessionDep):
    race = dbsession.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    race.state = 'Running'
    dbsession.add(race)
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
    return {"ok": True}


@app.get("/sessions/active/results")
def get_active_session_results(dbsession: SessionDep):
    from collections import defaultdict
    race_session = get_active_session(dbsession)

    races = dbsession.exec(
        select(Race)
        .where(Race.session_id == race_session.id, Race.state == 'Finished')
        .order_by(Race.id)
    ).all()

    if not races:
        return {"session_id": race_session.id, "scoring_method": race_session.scoring_method, "races": [], "drivers": []}

    race_ids = [r.id for r in races]

    all_driver_races = dbsession.exec(
        select(DriverRace).where(DriverRace.race_id.in_(race_ids))
    ).all()

    # Drop races that have no driver entries (finished without a lineup)
    races_with_data = {dr.race_id for dr in all_driver_races}
    races = [r for r in races if r.id in races_with_data]
    race_ids = [r.id for r in races]
    if not races:
        return {"session_id": race_session.id, "scoring_method": race_session.scoring_method, "races": [], "drivers": []}

    md_rows = dbsession.exec(
        select(MeetingDriver).where(MeetingDriver.meeting_id == race_session.meeting_id)
    ).all()
    meeting_driver_names = {md.driver_id: md.driver_name for md in md_rows}

    race_groups = defaultdict(list)
    for dr in all_driver_races:
        race_groups[dr.race_id].append(dr)

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

    scoring_method = race_session.scoring_method
    scoring_points_json = race_session.scoring_points
    dns_score = len(meeting_driver_names) + 1

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
        driver_rows.append({
            "driver_id": did,
            "driver_name": name,
            "positions": pos_map,
            "points": pts_map,
            "total_points": sum(pts_map.values()),
        })

    driver_rows.sort(key=lambda d: (
        -d["total_points"],
        sum(p if p is not None else dns_score for p in d["positions"].values()),
    ))

    return {
        "session_id": race_session.id,
        "scoring_method": scoring_method,
        "races": [{"race_id": r.id, "race_number": i + 1} for i, r in enumerate(races)],
        "drivers": driver_rows,
    }


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

