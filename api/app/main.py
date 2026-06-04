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
from next_race import get_drivers_for_next_race_sql, assign_drivers_to_lanes, load_pending_race, save_pending_race, get_active_meeting_id, get_active_meeting, get_active_session, session_with_state, set_lane_enabled

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
    with Session(engine) as session:
        yield session

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
def get_cars():
    car_pics_local_path = os.path.join(os.getcwd(), settings.CARS_MEDIA_FOLDER)
    car_pic_base_url = f"{settings.API_URL}/{settings.CARS_MEDIA_FOLDER}"
    files = [f"{car_pic_base_url}/{filename}" for filename in os.listdir(car_pics_local_path)]
    print(f"Car pics: {files}")
    return files


@app.get("/meetings")
def get_all_meetings(session: SessionDep):
    try:
        meetings = session.exec(select(Meeting)).all()
        return meetings
    except Exception as e:
        logger.error(f"Error retrieving meetings: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = { "message": str(e), "traceback": traceback.format_exc(), "model": str(Meeting.__dict__) }
        raise HTTPException(status_code=500, detail=error_detail)

@app.get("/meetings/active", response_model=Meeting)
def get_active_meeting_endpoint(session: SessionDep):
    return get_active_meeting(session)


@app.get("/meetings/upcoming")
def get_upcoming_meetings(session: SessionDep):
    try:
        meetings = session.exec(select(Meeting).where(Meeting.date >= datetime.now())).all()
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
    session: SessionDep, 
    meeting_id: int = Query(None, 
        description="Filter sessions by meeting ID",
    )
):
    try:
        if meeting_id is not None:
            race_sessions = session.exec(select(RaceSession).where(RaceSession.meeting_id == meeting_id)).all()
        else:
            race_sessions = session.exec(select(RaceSession)).all()
        return race_sessions
    except Exception as e:
        logger.error(f"Error retrieving sessions: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = { "message": str(e), "traceback": traceback.format_exc(), "model": str(RaceSession.__dict__) }
        raise HTTPException(status_code=500, detail=error_detail)


def get_lanes(session: SessionDep):
    try:
        lanes = session.exec(select(Lane).order_by(Lane.lane_number)).all()
        return lanes
    except Exception as e:
        logger.error(f"Error retrieving lanes: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)
    

@app.get("/sessions/active", response_model=RaceSessionWithState)
def get_active_session_endpoint(session: SessionDep):
    return session_with_state(get_active_session(session), session)


@app.get("/sessions/{session_id}", response_model=RaceSessionWithState)
def get_session(session_id: int, session: SessionDep):
    race_session = session.get(RaceSession, session_id)
    if not race_session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_with_state(race_session, session)


@app.patch("/sessions/{session_id}", response_model=RaceSession)
def update_session(session_id: int, session_update: RaceSessionUpdate, session: SessionDep):
    db_session = session.get(RaceSession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    update_data = session_update.model_dump(exclude_unset=True)
    db_session.sqlmodel_update(update_data)
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    return db_session


@app.get("/races/pending/")
def get_pending_race(session: SessionDep):
    existing = load_pending_race(session)
    if existing:
        return existing
    meeting_id = get_active_meeting_id(session)
    lanes = get_lanes(session)
    drivers = get_drivers_for_next_race_sql(session)
    setup = assign_drivers_to_lanes(drivers, lanes)
    return save_pending_race(session, setup, meeting_id)


@app.get("/drivers/nextrace/")
def get_drivers_for_next_race(session: SessionDep):
    lanes = get_lanes(session)
    drivers = get_drivers_for_next_race_sql(session)
    return assign_drivers_to_lanes(drivers, lanes)



@app.post("/drivers/")
def create_driver(driver: Driver, session: SessionDep) -> Driver:
    session.add(driver)
    session.commit()
    session.refresh(driver)
    return driver

@app.get("/drivers/")
def get_all_drivers(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
) -> list[Driver]:
    drivers = session.exec(select(Driver).offset(offset).limit(limit)).all()
    return drivers

@app.get("/drivers/{driver_id}")
def get_driver(driver_id: int, session: SessionDep) -> Driver:
    driver = session.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver

@app.delete("/drivers/{driver_id}")
def delete_driver(driver_id: int, session: SessionDep):
    driver = session.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    session.delete(driver)
    session.commit()
    return {"ok": True}




@app.patch("/lanes/{lane_number}")
def patch_lane(lane_number: int, update: LaneUpdate, session: SessionDep):
    return set_lane_enabled(session, lane_number, update.enabled)


@app.post("/races/{race_id}/start")
def start_race(race_id: int, session: SessionDep):
    race = session.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    race.state = 'Running'
    session.add(race)
    session.commit()
    return {"ok": True}


@app.post("/races/{race_id}/finish")
def finish_race(race_id: int, session: SessionDep):
    race = session.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    race.state = 'Finished'
    session.add(race)
    session.commit()
    return {"ok": True}


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

