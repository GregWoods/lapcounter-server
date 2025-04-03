from typing import Optional
from decimal import Decimal
from datetime import date, datetime, time
from sqlmodel import Field, SQLModel, create_engine, UniqueConstraint

class DriverWithLane(SQLModel):
    id: int = 0
    first_name: str = ""
    last_name: str = ""
    completed_races: int = 0
    sit_out_next_race: bool = False
    lane1_count: int = 0
    lane2_count: int = 0
    lane3_count: int = 0
    lane4_count: int = 0
    lane5_count: int = 0
    lane6_count: int = 0
    random_value: float = 0.0
    lane_number: int = 0
    lane_color: str = ""
    lane_enabled: bool = True


    @classmethod
    def create(cls, *, driver=None, lane=None):
        """Factory method to create a new driver with lane
        
        Args:
            lane: Lane information to add
            driver: Driver information to copy
        """
        driver_with_lane = cls()

        if driver is not None:
            driver_attrs = [
                'id', 'first_name', 'last_name', 'completed_races', 
                'sit_out_next_race', 'lane1_count', 'lane2_count', 
                'lane3_count', 'lane4_count', 'lane5_count', 'lane6_count',
                'random_value'
            ]
            for attr in driver_attrs:
                setattr(driver_with_lane, attr, getattr(driver, attr))

        if lane is not None:
            driver_with_lane.lane_number = lane.lane_number
            driver_with_lane.lane_color = lane.color
            driver_with_lane.lane_enabled = lane.enabled

        return driver_with_lane


    @classmethod
    def create_blank(cls):
        """Factory method to create a blank driver"""
        return cls()
    

    def add_lane(self, lane):
        """Add lane to driver"""
        if lane is not None:
            self.lane_number = lane.lane_number
            self.lane_color = lane.color
            self.lane_enabled = lane.enabled
    

    def add_driver_to_lane(self, driver):
        driver_attrs = [
            'id', 'first_name', 'last_name', 'completed_races', 
            'sit_out_next_race', 'lane1_count', 'lane2_count', 
            'lane3_count', 'lane4_count', 'lane5_count', 'lane6_count',
            'random_value'
        ]
        for attr in driver_attrs:
            setattr(self, attr, getattr(driver, attr))


class NextRaceSetup(SQLModel):
    next_race_drivers: list[DriverWithLane] = []
    other_drivers: list[DriverWithLane] = []


