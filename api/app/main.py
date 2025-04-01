import os
import logging
import traceback
import random
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Annotated, Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from settings import Settings
from model import *
from responsemodel import NextRaceSetup, DriverWithLane

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


#def assign_unique_lanes(drivers, available_lanes):
#    # Randomize the initial order of lanes
#    #random.seed(42)  # use a seed when unit testing
#    random.shuffle(available_lanes)
#    
#    # Process each driver in order
#    for driver in drivers:
#        # Find the driver's least used lane among available lanes
#        driver.lane_number = min(available_lanes, key=lambda x: getattr(driver, f"lane{x}_count"))
#        
#        # Remove the assigned lane from available lanes
#        available_lanes.remove(driver.lane_number)


def get_drivers_for_next_race_sql(session: SessionDep):
    try:
        #if testing:
        #    seed_query = text("SELECT setseed(0.42)")
        #    session.exec(seed_query)

        from sqlalchemy import text
        query = text("""
            SELECT 
                d.id,
                d.first_name, 
                d.last_name,
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
                driver_races dr ON d.id = dr.driver_id
            LEFT JOIN 
                races r ON dr.race_id = r.id AND r.state = 'Finished'
            GROUP BY 
                d.id, d.first_name, d.last_name, d.sit_out_next_race
            ORDER BY 
                sit_out_next_race ASC, 
                completed_races ASC,
                random_value ASC
        """)
        return session.exec(query)
    except Exception as e:
        logger.error(f"Error retrieving drivers for next race: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)



#The unit-testable logic for sorting drivers into racing and non-racing groups
#  No dependencies on the database or the api routing magic
def assign_drivers_to_lanes(driver_list, lanes):
    # Initialize lists for racing and non-racing drivers
    lanes_with_drivers = []
    drivers_not_racing = []

    # Create a copy of driver_list that we can modify
    available_drivers = list(driver_list)

    # Randomise the order of lanes to reduce the chances of a driver being assigned to the same lane too often
    random.shuffle(lanes)

    

    for lane in lanes:
        if lane.enabled and available_drivers:
            # Get first available driver who is not sitting out
            # (Drivers are sorted, with available drivers first)
            # Check if the driver is sitting out
            if available_drivers[0].sit_out_next_race:
                # Assign a blank driver to this lane
                lanes_with_drivers.append(DriverWithLane.create_blank(lane))
                # and move the driver into the not_racing list
                drivers_not_racing.append(DriverWithLane.create_from_driver(available_drivers.pop(0), lane))
            else:
                # A driver is available. Assign him to the lane
                lanes_with_drivers.append(DriverWithLane.create_from_driver(available_drivers.pop(0), lane))
        else:
            # Either lane is disabled, or no drivers are left... add a blank driver to this lane
            lanes_with_drivers.append(DriverWithLane.create_blank(lane))

    # Sort lanes_with_drivers by lane number
    lanes_with_drivers.sort(key=lambda driver: driver.lane_number)

    # Assign all drivers left in available_drivers to the not_racing list
    for driver in available_drivers:
        # Create a new DriverWithLane object for each driver
        not_racing_driver = DriverWithLane.create_from_driver(driver, None) 
        drivers_not_racing.append(not_racing_driver)

    # Order other_drivers by completed_races only... once we've filled all the lanes
    #   we don't care if they are sitting out or not.
    drivers_not_racing.sort(key=lambda driver: driver.completed_races)

    return NextRaceSetup(
        next_race_drivers=lanes_with_drivers,
        other_drivers=drivers_not_racing
    )

def get_lanes(session: SessionDep):
    try:
        lanes = session.exec(select(Lane).order_by(Lane.lane_number)).all()
        return lanes
    except Exception as e:
        logger.error(f"Error retrieving lanes: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)
    

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

