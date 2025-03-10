from typing import Optional
from decimal import Decimal
from datetime import date, datetime
from sqlmodel import Column, Field, Integer, Identity, Session, SQLModel, create_engine, select, UniqueConstraint
#from sqlalchemy import Table, Column, MetaData, Integer, Computed



class CarManufacturer(SQLModel, table=True):
    __tablename__ = "car_manufacturers"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class CarCategory(SQLModel, table=True):
    __tablename__ = "car_categories"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)


class CarModel(SQLModel, table=True):
    __tablename__ = "car_models"
    id: Optional[int] = Field(default=None, primary_key=True)
    car_category_id: Optional[int] = Field(default=None, foreign_key="car_categories.id")
    manufacturer_id: Optional[int] = Field(default=None, foreign_key="car_manufacturers.id")
    name: str
    race_number: Optional[str]
    model_number: Optional[str]

class CarTyre(SQLModel, table=True):
    __tablename__ = "car_tyres"
    id: Optional[int] = Field(default=None, primary_key=True)
    brand: str
    compound: Optional[str]
    size: Optional[str]

class ChipHardware(SQLModel, table=True):
    __tablename__ = "chip_hardwares"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str



class ChipFirmware(SQLModel, table=True):
    __tablename__ = "chip_firmwares"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

class Car(SQLModel, table=True):
    __tablename__ = "cars"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    car_model_id: Optional[int] = Field(default=None, foreign_key="car_models.id")
    tyre_id: Optional[int] = Field(default=None, foreign_key="car_tyres.id")
    magnet: bool
    weight_added: float
    modifications_notes: Optional[str]
    chip_hardware_id: Optional[int] = Field(default=None, foreign_key="chip_hardwares.id")
    chip_firmware_id: Optional[int] = Field(default=None, foreign_key="chip_firmwares.id")
    picture: Optional[str]
    rfid: Optional[str]


class Driver(SQLModel, table=True):
    __tablename__ = "drivers"
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str
    last_name: Optional[str]
    mobile_number: Optional[str]
    picture: Optional[str]
    rfid: Optional[str]

class Meeting(SQLModel, table=True):
    __tablename__ = "meetings"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    date: date
    venue: Optional[str]

class MeetingDriver(SQLModel, table=True):
    __tablename__ = "meeting_drivers"
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id", primary_key=True)
    driver_id: Optional[int] = Field(default=None, foreign_key="drivers.id", primary_key=True)
    driver_name: str    #Generated. Usually just first_name, but may include last_name initial if 2 drivers have the same first name


class MeetingCar(SQLModel, table=True):
    __tablename__ = "meeting_cars"
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id", primary_key=True)
    car_id: Optional[int] = Field(default=None, foreign_key="cars.id", primary_key=True)


class Session(SQLModel, table=True): 
    __tablename__ = "sessions"
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id")
    session_type: str               # 'Points', 'FastestLap', 'Championship'
    end_condition: str              # 'Laps', 'Time'
    end_condition_info: Optional[int]   #number of laps or time  in minutes
    scoring_method: str             # 'LapPoints', 'PositionPoints', 'FastestLap'
    scoring_points: Optional[str]   # JSON string with points array used for PositionPoints (and FastestLap points?)
    start_time: Optional[datetime]
    end_time: Optional[datetime]


class Race(SQLModel, table=True):
    __tablename__ = "races"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[int] = Field(default=None, foreign_key="sessions.id")
    state: str          # 'NotStarted', 'Running', 'Finished'


# Links drivers with their cars for a particular race,
#   and links all drivers who are racing together.
# Does not store any lap related data, which can all be derived from driver_lap
class DriverRace(SQLModel, table=True):
    __tablename__ = "driver_races"
    __table_args__ = (
        UniqueConstraint("driver_id", "race_id", name="unique_driver_race"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    driver_id: Optional[int] = Field(default=None, foreign_key="drivers.id")
    race_id: Optional[int] = Field(default=None, foreign_key="races.id")
    car_id: Optional[int] = Field(default=None, foreign_key="cars.id")
    # For later use
    laps_completed: Optional[int]
    last_lap_time: Optional[Decimal] = Field(default=0, max_digits=10, decimal_places=3)
    fastest_lap_time: Optional[Decimal] = Field(default=0, max_digits=10, decimal_places=3)


class DriverLap(SQLModel, table=True):
    __tablename__ = "driver_laps"
    id: Optional[int] = Field(default=None, primary_key=True)
    driver_race_id: Optional[int] = Field(default=None, foreign_key="driver_races.id")
    #Used only for sorting, not for calculations
    created_at: datetime = Field(default=datetime.now)
    lap_time: Decimal = Field(default=0, max_digits=10, decimal_places=3)
    #lap_number can be derived


# not using relationships yet
#  https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/define-relationships-attributes/#declare-relationship-attributes


# localhost" will be "database" on live/docker env... so need it in an env var
dbHost = "localhost"
engine = create_engine(f"postgresql://{dbHost}/lapcounter_server?user=lap&password=lap", echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    create_db_and_tables()
