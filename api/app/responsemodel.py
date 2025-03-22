from typing import Optional
from decimal import Decimal
from datetime import date, datetime, time
from sqlmodel import Field, SQLModel, create_engine, UniqueConstraint

class DriverForNextRace(SQLModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    completed_races: int = 0
    lane: int = 0
    sit_out_next_race: bool = False
    lane1_count: int = 0
    lane2_count: int = 0
    lane3_count: int = 0
    lane4_count: int = 0
    lane5_count: int = 0
    lane6_count: int = 0
    random_value: float = 0.0
    lane: Optional[int] = None
