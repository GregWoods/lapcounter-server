import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Annotated, Optional
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Field, Session, SQLModel, create_engine, select

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

settings = Settings()


@app.get("/api/settings")
async def info():
    return settings.REACT_URL


@app.get("/api/cars")
def get_cars():
    car_pics_local_path = os.path.join(os.getcwd(), settings.CARS_MEDIA_FOLDER)
    car_pic_base_url = f"{settings.API_URL}/{settings.CARS_MEDIA_FOLDER}"
    files = [f"{car_pic_base_url}/{filename}" for filename in os.listdir(car_pics_local_path)]
    print(f"Car pics: {files}")
    return files


# CREATE TABLE drivers (
#     id SERIAL PRIMARY KEY,
#     first_name VARCHAR(255) NOT NULL,
#     last_name VARCHAR(255) NOT NULL,
#     mobile_number VARCHAR(20),
#     picture VARCHAR(255),   -- Filename of driver pic. No path or url
#     rfid VARCHAR(255)
# );
class Driver(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    first_name: str
    last_name: str
    mobile_number: Optional[str] = None
    picture: Optional[str] = None
    rfid: Optional[str] = None


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]

#asyncio_engine = create_async_engine(
engine = create_engine(
    "postgresql+psycopg://scott:tiger@localhost/test",
    connect_args={"check_same_thread": False}
)

app = FastAPI()
app.mount("/media", StaticFiles(directory="media"), name="media")

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

#@app.on_event("startup")
#def on_startup():
#    create_db_and_tables()


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







