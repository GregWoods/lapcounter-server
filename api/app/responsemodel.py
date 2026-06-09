from typing import Optional
from decimal import Decimal
from datetime import date, datetime, time
from sqlmodel import Field, SQLModel, create_engine, UniqueConstraint

class DriverWithLane(SQLModel):
    id: int = 0
    driver_name: str = ""
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
    car_picture: str = ""  # car image filename for this lane, e.g. "GT_Porsche_Black.jpg"


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
                'id', 'driver_name', 'completed_races', 
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
            'id', 'driver_name', 'completed_races', 
            'sit_out_next_race', 'lane1_count', 'lane2_count', 
            'lane3_count', 'lane4_count', 'lane5_count', 'lane6_count',
            'random_value'
        ]
        for attr in driver_attrs:
            setattr(self, attr, getattr(driver, attr))


class RaceSessionWithState(SQLModel):
    id: Optional[int]
    meeting_id: Optional[int]
    session_type: str
    end_condition: str
    end_condition_info: Optional[int]
    scoring_method: str
    scoring_points: Optional[str]
    start_time: Optional[time]
    end_time: Optional[time]
    state: str  # 'NotStarted', 'InProgress', 'Finished'


class NextRaceSetup(SQLModel):
    race_id: int = 0
    race_number: int = 1
    count_first_crossing: bool = False
    lane_assignments: list[DriverWithLane] = []
    other_drivers: list[DriverWithLane] = []


