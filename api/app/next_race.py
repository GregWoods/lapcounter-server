import logging
import traceback
import random
from typing import List
from fastapi import HTTPException
from model import *
from responsemodel import NextRaceSetup, DriverWithLane
from pprint import pprint


logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)


def get_drivers_for_next_race_sql(session):
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
        rows = session.exec(query).all()
        # Convert SQL rows to DriverWithLane objects
        drivers = []
        for row in rows:
            driver = DriverWithLane(
                id=row.id,
                first_name=row.first_name,
                last_name=row.last_name,
                sit_out_next_race=row.sit_out_next_race,
                completed_races=row.completed_races,
                lane1_count=row.lane1_count,
                lane2_count=row.lane2_count,
                lane3_count=row.lane3_count,
                lane4_count=row.lane4_count,
                lane5_count=row.lane5_count,
                lane6_count=row.lane6_count,
                random_value=row.random_value
            )
            drivers.append(driver)
        return drivers
    except Exception as e:
        logger.error(f"Error retrieving drivers for next race: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)


#The unit-testable logic for sorting drivers into racing and non-racing groups
#  No dependencies on the database or the api routing magic
def assign_drivers_to_lanes(driver_list: List[DriverWithLane], lanes: List[Lane]):
    """
    Assign drivers to lanes for the next race, optimizing lane assignments.
    
    Args:
        driver_list: List of DriverWithLane objects from the database
        lanes: List of Lane objects representing physical lanes
        
    Returns:
        NextRaceSetup with racing drivers assigned to lanes and remaining drivers
    """
    # Create a copy of driver_list that we can modify
    available_drivers = list(driver_list)

    # Get enabled lanes and determine how many drivers we need
    enabled_lanes = [lane for lane in lanes if lane.enabled]

    # Get all drivers who aren't sitting out
    available_racing_drivers = [d for d in available_drivers if not d.sit_out_next_race]
    
    # Determine how many drivers we need (min of enabled lanes and available available_racing_drivers)
    num_racing_drivers = min(len(enabled_lanes), len(available_racing_drivers))

    # Take the top N drivers who aren't sitting out, sorted by completed_races
    # (they're already sorted by completed_races from the SQL query)
    racing_drivers = available_racing_drivers[:num_racing_drivers]

    # All other drivers go into drivers_not_racing
    racing_driver_ids = {d.id for d in racing_drivers}
    drivers_not_racing = [d for d in available_drivers if d.id not in racing_driver_ids]

    # Create a list of blank drivers with lanes
    lane_assignments = []
    for lane in lanes:
        lane_assignments.append(DriverWithLane.create(lane=lane))
    random.shuffle(lane_assignments)

    # assign drivers to lane
    for lane in lane_assignments:
        # get a driver who has used this lane the least number of times
        racing_drivers.sort(key=lambda driver: getattr(driver, f"lane{lane.lane_number}_count"))
        #lanes_with_drivers.append(DriverWithLane.create(driver=racing_drivers.pop(0), lane))
        if len(racing_drivers) > 0:
            lane.add_driver_to_lane(racing_drivers.pop(0))

    # Sort lanes_with_drivers by lane number
    lane_assignments.sort(key=lambda driver: driver.lane_number)

    # Order other_drivers by completed_races only... once we've filled all the lanes
    #   we don't care if they are sitting out or not.
    drivers_not_racing.sort(key=lambda driver: driver.completed_races)

    return NextRaceSetup(
        lane_assignments=lane_assignments,
        other_drivers=drivers_not_racing
    )
