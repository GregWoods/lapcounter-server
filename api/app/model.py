from typing import Optional
import uuid
from decimal import Decimal
import datetime as _datetime
from datetime import date, datetime, time, timezone
from sqlmodel import Field, SQLModel, create_engine, UniqueConstraint
from sqlalchemy import BigInteger, Column, DateTime, text

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
    sit_out_next_race: bool = Field(default=False)


class Meeting(SQLModel, table=True):
    __tablename__ = "meetings"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    date: date
    venue: Optional[str]
    # Set when the operator ends the meeting. An unended meeting stays active whatever its
    # date says; see get_active_meeting(). TIMESTAMPTZ in the schema, so tz-aware here.
    ended_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Unguessable id for guest-facing URLs (/m/<public_id>/...).
    public_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column_kwargs={"unique": True, "server_default": text("gen_random_uuid()")},
    )


class MeetingDriver(SQLModel, table=True):
    __tablename__ = "meeting_drivers"
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id", primary_key=True)
    driver_id: Optional[int] = Field(default=None, foreign_key="drivers.id", primary_key=True)
    driver_name: str    #Usually just first_name, but may include last_name initial if 2 drivers have the same first name
    #Note: when a driver is added to a meeting, driver_names for that meeting need to be recalculated

class MeetingCar(SQLModel, table=True):
    __tablename__ = "meeting_cars"
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id", primary_key=True)
    car_id: Optional[int] = Field(default=None, foreign_key="cars.id", primary_key=True)
    lane: Optional[int] = Field(default=None)   # default lane assignment for this car at this meeting (1-6, nullable for spare cars)


class RaceSession(SQLModel, table=True):
    __tablename__ = "sessions"  #To be renamed to race_sessions
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id")
    session_type: str               # 'Points', 'FastestLap', 'Championship'
    end_condition: str              # per-race end: 'Laps' (Finishing Position) or 'Time' (Fastest Lap)
    end_condition_info: Optional[int]   #number of laps or time  in minutes
    races_per_driver: Optional[int] = Field(default=None)  # automatic session end: each driver races this many times (None = manual end)
    max_sit_outs: Optional[int] = Field(default=None)  # skips before a driver is offered up for disqualification (None = no limit)
    yellow_grace_seconds: int = Field(default=5)  # full-power seconds after a yellow flag before power cuts (BLE only; no-op on GPIO)
    yellow_grace_power_pct: int = Field(default=100)  # % power during the grace period (BLE only; locked to 100 without power_control)
    yellow_post_grace_power_pct: int = Field(default=0)  # % power once the grace period expires (BLE only; locked to 100 without power_control)
    yellow_lap_penalty_laps: int = Field(default=0)  # laps deducted for crossing after grace expiry (GPIO-only substitute; Points sessions only, 0 = no penalty)
    min_lap_time: float = Field(default=3.0)  # seconds; lapdata drops crossings closer together than this as phantom triggers
    start_grid: str = Field(default='BehindLine')   # 'InFrontOfLine' or 'BehindLine' — which crossing ends lap 1 (see CLAUDE.md "Discarded first crossing")
    scoring_method: str             # 'PositionPoints' (Finishing Position) or 'FastestLap' (personal best)
    scoring_points: Optional[str]   # JSON string with points array used for PositionPoints
    start_time: Optional[time]
    end_time: Optional[time]
    state: str = Field(default='NotStarted')  # 'NotStarted', 'InProgress', 'Finished'


class Race(SQLModel, table=True):
    __tablename__ = "races"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[int] = Field(default=None, foreign_key="sessions.id")
    race_number: Optional[int] = Field(default=None)
    state: str          # 'NotStarted', 'Running', 'Finished'
    # Lights-out instant, from lapdata's race_start_time. Written tz-aware (UTC), so it
    # needs an explicit sa_column: a bare `Optional[datetime]` maps to TIMESTAMP WITHOUT
    # TIME ZONE, which doesn't match the schema's TIMESTAMPTZ.
    started_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


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
    lane: int = Field(default=0)    #1 to 6
    # For later use
    laps_completed: Optional[int]
    last_lap_time: Optional[Decimal] = Field(default=None)
    fastest_lap_time: Optional[Decimal] = Field(default=None)


# Records an operator withdrawal of a driver from a race (the NextRace "×" button).
# Written when a driver is removed from a race lineup; cleared if the same driver is
# re-added to that race, and deleted with the race when a NotStarted queue is discarded.
# A withdrawal attached to a *Finished* race counts as one "skip" for the driver in that
# session — that's how skips are effectively counted at race-finish time. Rotation (a
# driver the scheduler simply didn't include this race) leaves no withdrawal, so it never
# counts as a skip.
class RaceWithdrawal(SQLModel, table=True):
    __tablename__ = "race_withdrawals"
    race_id: Optional[int] = Field(default=None, foreign_key="races.id", primary_key=True)
    driver_id: Optional[int] = Field(default=None, foreign_key="drivers.id", primary_key=True)


# Per-session, per-driver state. Currently just holds the disqualified flag: a driver who
# has sat out too many races (skips >= session.max_sit_outs) and whom the operator has
# chosen to remove from the rest of the session. Disqualified drivers are excluded from
# all further scheduling for that session (unlike the global, one-race Driver.sit_out_next_race).
class SessionDriver(SQLModel, table=True):
    __tablename__ = "session_drivers"
    session_id: Optional[int] = Field(default=None, foreign_key="sessions.id", primary_key=True)
    driver_id: Optional[int] = Field(default=None, foreign_key="drivers.id", primary_key=True)
    disqualified: bool = Field(default=False)


class DriverLap(SQLModel, table=True):
    __tablename__ = "driver_laps"
    id: Optional[int] = Field(default=None, primary_key=True)
    driver_race_id: Optional[int] = Field(default=None, foreign_key="driver_races.id")
    #Used only for sorting, not for calculations
    # The schema gives this a DB default (dbwriter inserts raw SQL); server_default says
    # so here too. A table built from this model once had none, and lost every lap (#84).
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )
    # NULL for a void crossing: only 'counted' rows are laps (migration 003, #86).
    lap_time: Optional[Decimal] = Field(default=None)
    # 'counted', 'start_line', 'yellow_flag' or 'baseline' — what lapdata made of the crossing.
    # Anything counting laps or taking a fastest lap must filter to 'counted'.
    outcome: str = Field(default='counted', sa_column_kwargs={"server_default": text("'counted'")})
    # Lap-timing provenance (#27), on void crossings too. counter_ms on one clock is the
    # crossing's exact instant; crossed_at is it as wall-clock time, for reading only.
    clock: Optional[str] = Field(default=None)
    counter_ms: Optional[int] = Field(default=None, sa_type=BigInteger)
    crossed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    #lap_number can be derived


class Lane(SQLModel, table=True):
    __tablename__ = "lanes"
    lane_number: Optional[int] = Field(default=None, primary_key=True)
    color: str
    enabled: bool = Field(default=True)


class LaneUpdate(SQLModel):
    enabled: bool


class LaneCarUpdate(SQLModel):
    car_id: Optional[int] = None


class PendingRaceAddDriver(SQLModel):
    driver_id: int


class RaceSessionUpdate(SQLModel):
    session_type: Optional[str] = None
    end_condition: Optional[str] = None
    end_condition_info: Optional[int] = None
    races_per_driver: Optional[int] = None
    max_sit_outs: Optional[int] = None
    yellow_grace_seconds: Optional[int] = None
    yellow_grace_power_pct: Optional[int] = None
    yellow_post_grace_power_pct: Optional[int] = None
    yellow_lap_penalty_laps: Optional[int] = None
    min_lap_time: Optional[float] = None
    start_grid: Optional[str] = None
    scoring_method: Optional[str] = None
    scoring_points: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


class MeetingCreate(SQLModel):
    name: str
    date: date
    venue: Optional[str] = None


class MeetingUpdate(SQLModel):
    name: Optional[str] = None
    # `Optional[date]` here resolves `date` to the field's own `None` default, so every
    # real date was rejected ("Input should be None"). Name the type via the module.
    date: Optional[_datetime.date] = None
    venue: Optional[str] = None


class RaceSessionCreate(SQLModel):
    meeting_id: int
    session_type: str
    end_condition: str
    end_condition_info: Optional[int] = None
    races_per_driver: Optional[int] = None
    max_sit_outs: Optional[int] = None
    yellow_grace_seconds: int = 5
    yellow_grace_power_pct: int = 100
    yellow_post_grace_power_pct: int = 0
    yellow_lap_penalty_laps: int = 0
    min_lap_time: float = 3.0
    start_grid: str = 'BehindLine'
    scoring_method: str
    scoring_points: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


# A penalty applied by lapdata's race manager (currently only a yellow-flag lap penalty
# for Points sessions) so it survives past the race and factors into
# build_session_results() instead of only affecting live race_state. Written by dbwriter
# from the `driver_penalty` MQTT topic (#88).
class RacePenalty(SQLModel, table=True):
    __tablename__ = "race_penalties"
    id: Optional[int] = Field(default=None, primary_key=True)
    race_id: Optional[int] = Field(default=None, foreign_key="races.id")
    driver_id: Optional[int] = Field(default=None, foreign_key="drivers.id")
    penalty_type: str    # 'lap' only for now
    amount: Decimal
    reason: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AppSetting(SQLModel, table=True):
    """Installation-wide key/value setting; see app_settings.py for the known keys."""
    __tablename__ = "app_settings"
    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(max_length=255)


# not using relationships yet
#  https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/define-relationships-attributes/#declare-relationship-attributes





