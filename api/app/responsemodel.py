from typing import Optional
from decimal import Decimal
from datetime import date, datetime, time
from sqlmodel import Field, SQLModel, create_engine, UniqueConstraint

class DriverForNextRace(SQLModel):
    def __init__(self, id=None, first_name="", last_name=None, 
                 completed_races=0, sit_out_next_race=False,
                 lane1_count=0, lane2_count=0, lane3_count=0,
                 lane4_count=0, lane5_count=0, lane6_count=0, 
                 random_value=0.0):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.completed_races = completed_races
        self.sit_out_next_race = sit_out_next_race
        self.lane1_count = lane1_count
        self.lane2_count = lane2_count
        self.lane3_count = lane3_count
        self.lane4_count = lane4_count
        self.lane5_count = lane5_count
        self.lane6_count = lane6_count
        self.random_value = random_value

    id: int
    first_name: str
    last_name: Optional[str]
    completed_races: int
    sit_out_next_race: bool
    lane1_count: int
    lane2_count: int
    lane3_count: int
    lane4_count: int
    lane5_count: int
    lane6_count: int
    random_value: float
