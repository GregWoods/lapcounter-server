from typing import Optional
from decimal import Decimal
from datetime import date, datetime, time
from sqlmodel import Field, SQLModel, create_engine, UniqueConstraint

#class Lane(SQLModel):
#    lane_number: Optional[int] = Field(default=None, primary_key=True)
#    color: str
#    enabled: bool = Field(default=True)


class DriverWithLane(SQLModel):
    id: int = 0
    first_name: str = ""
    last_name: Optional[str] = None
    completed_races: int = 0
    sit_out_next_race: bool = False
    lane1_count: int = 0
    lane2_count: int = 0
    lane3_count: int = 0
    lane4_count: int = 0
    lane5_count: int = 0
    lane6_count: int = 0
    random_value: float = 0.0
    lane_number: Optional[int] = None
    lane_color: Optional[str] = None
    lane_enabled: Optional[bool] = None

    @classmethod
    def create_from_driver(cls, driver, lane):
        """Factory method to create a new driver"""
        driver_with_lane = cls(
            id = driver.id,
            first_name = driver.first_name,
            last_name = driver.last_name,
            completed_races = driver.completed_races,
            sit_out_next_race = driver.sit_out_next_race,
            lane1_count = driver.lane1_count,
            lane2_count = driver.lane2_count,
            lane3_count = driver.lane3_count,
            lane4_count = driver.lane4_count,
            lane5_count = driver.lane5_count,
            lane6_count = driver.lane6_count,
            random_value = driver.random_value
        )
        
        if lane is not None:
            driver_with_lane.lane_number = lane.lane_number
            driver_with_lane.lane_color = lane.color
            driver_with_lane.lane_enabled = lane.enabled
        
        return driver_with_lane

    @classmethod
    def create_blank(cls):
        """Factory method to create a blank driver"""
        return cls()



class NextRaceSetup(SQLModel):
    next_race_drivers: list[DriverWithLane] = []
    other_drivers: list[DriverWithLane] = []


