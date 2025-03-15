import os
import logging
import traceback
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Annotated, Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from model import * 

class Settings(BaseSettings):
    API_URL: str
    REACT_URL: str
    MEDIA_FOLDER: str
    CARS_MEDIA_FOLDER: str
    DB_DATABASE: str
    DB_HOST: str
    DB_USER: str
    DB_PASSWORD: str
    DB_PORT: int
    model_config = SettingsConfigDict(env_file=".env")


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

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

#if __name__ == "__main__":
#    create_db_and_tables()

#@app.on_event("startup")
#def on_startup():
#    create_db_and_tables()

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


@app.get("/verify-db")
def verify_db():
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return {"status": "connected", "tables": tables}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# NEXT: GET Meetings
@app.get("/meetings")
def read_meetings(session: SessionDep):
    try:
        # Print meeting class information for debugging
        print(f"Meeting class: {Meeting}")
        print(f"Meeting.__tablename__: {getattr(Meeting, '__tablename__', None)}")
        
        # Try to manually execute a simple SQL query to test the connection
        result = session.execute("SELECT 1").fetchone()
        print(f"Test query result: {result}")
        
        # Create query and print it
        query = select(Meeting)
        print(f"Query: {query}")
        
        # Execute query and print results
        meetings = session.exec(query).all()
        print(f"Meetings found: {len(meetings)}")
        
        return meetings
    except Exception as e:
        logger.error(f"Error retrieving meetings: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Return detailed error information
        error_detail = {
            "message": str(e),
            "traceback": traceback.format_exc(),
            "meeting_model": str(Meeting.__dict__),
        }
        
        raise HTTPException(status_code=500, detail=error_detail)

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




@app.get("/diagnose-meeting-issue")
def diagnose_meeting_issue(session: SessionDep):
    results = {}
    
    # Step 1: Check if session works
    try:
        results["basic_query"] = str(session.execute("SELECT 1").fetchone())
    except Exception as e:
        results["basic_query_error"] = str(e)
    
    # Step 2: Check Meeting class
    try:
        results["meeting_class"] = str(Meeting.__dict__)
        results["meeting_tablename"] = getattr(Meeting, "__tablename__", "Not found")
    except Exception as e:
        results["meeting_class_error"] = str(e)
    
    # Step 3: Check if meetings table exists and content
    try:
        raw_results = session.execute("SELECT COUNT(*) FROM meetings").fetchone()
        results["table_count"] = raw_results[0]
    except Exception as e:
        results["table_query_error"] = str(e)
    
    # Step 4: Try to construct a query
    try:
        query = select(Meeting)
        results["query_str"] = str(query)
    except Exception as e:
        results["query_construction_error"] = str(e)
    
    return results

#@app.get("/heroes/")
#def read_heroes(
#    session: SessionDep,
#    offset: int = 0,
#    limit: Annotated[int, Query(le=100)] = 100,
#) -> list[Hero]:
#    heroes = session.exec(select(Hero).offset(offset).limit(limit)).all()
#    return heroes




# Driver CRUD Endpoints
@app.post("/drivers/")
def create_driver(driver: Driver, session: SessionDep) -> Driver:
    session.add(driver)
    session.commit()
    session.refresh(driver)
    return driver

@app.get("/drivers/")
def read_drivers(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
) -> list[Driver]:
    drivers = session.exec(select(Driver).offset(offset).limit(limit)).all()
    return drivers

@app.get("/drivers/{driver_id}")
def read_driver(driver_id: int, session: SessionDep) -> Driver:
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



@app.get("/raw-meetings")
def raw_meetings(session: SessionDep):
    try:
        # Use raw SQL instead of SQLModel
        result = session.execute("SELECT * FROM meetings LIMIT 10").fetchall()
        
        # Convert to dictionary
        columns = session.execute("SELECT column_name FROM information_schema.columns WHERE table_name='meetings'").fetchall()
        column_names = [col[0] for col in columns]
        
        meetings = []
        for row in result:
            meeting_dict = {column_names[i]: value for i, value in enumerate(row)}
            meetings.append(meeting_dict)
            
        return meetings
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


# Add this temporary model to main.py (not model.py)
class SimpleMeeting(SQLModel, table=True):
    __tablename__ = "meetings"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    
@app.get("/simple-meetings")
def simple_meetings(session: SessionDep):
    try:
        # Use the simple model
        results = session.exec(select(SimpleMeeting)).all()
        return results
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
    

@app.get("/import-check")
def import_check():
    import sys
    modules = [name for name in sys.modules if "model" in name.lower()]
    return {"modules": modules}    