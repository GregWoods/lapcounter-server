import logging
import traceback
import random
from fastapi import HTTPException
from model import *
from responsemodel import NextRaceSetup, DriverWithLane


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
        return session.exec(query)
    except Exception as e:
        logger.error(f"Error retrieving drivers for next race: {str(e)}")
        logger.error(traceback.format_exc())
        error_detail = {"message": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail=error_detail)



#The unit-testable logic for sorting drivers into racing and non-racing groups
#  No dependencies on the database or the api routing magic
def assign_drivers_to_lanes(driver_list, lanes):
    # Initialize lists for racing and non-racing drivers
    lanes_with_drivers = []
    drivers_not_racing = []

    # Create a copy of driver_list that we can modify
    available_drivers = list(driver_list)

    # we may have less than 6 available lanes
    # we may have less than 6 available, and not sitting out drivers
    # we need the lower of these two numbers, then pop that number off the top of the available_drivers list
    # and put then in a temporary available_racing_drivers list
    # loop through lanes
    # for each lane, sort available_racing_drivers by laneX_count ASC
    # and pop that driver off the top of the available_racing_drivers list and assign them to the lane in lanes_with_drivers

    # Get enabled lanes
    enabled_lanes = [lane for lane in lanes if lane.enabled]
    enabled_lane_count = len(enabled_lanes)

    # Get up to 'enabled_lane_count' drivers who aren't sitting out
    available_racing_drivers = [d for d in available_drivers if not d.sit_out_next_race][:enabled_lane_count]
    
    # Add all unassigned drivers to drivers_not_racing
    racing_driver_ids = {driver.id for driver in available_racing_drivers}
    drivers_not_racing = [d for d in available_drivers if d.id not in racing_driver_ids]

    # we now have exactly the correct number of drivers in available_racing_drivers
    #   taking into account the number of enabled lanes and the number of available drivers who are not sitting out
    # drivers_not_racing is finalised
    # we just need to assign lanes to available_racing_drivers

    random.shuffle(enabled_lanes)
    # trim the number of enabled_lanes to match the number of available_racing_drivers
    enabled_lanes = enabled_lanes[:len(available_racing_drivers)]

    for lane in enabled_lanes:
        # get a driver who has used this lane the least number of times
        available_racing_drivers.sort(key=lambda driver: getattr(driver, f"lane{lane.lane_number}_count"))
        lanes_with_drivers.append(DriverWithLane.create_from_driver(available_racing_drivers.pop(0), lane))

    # Finally, sort lanes_with_drivers by lane number
    lanes_with_drivers.sort(key=lambda driver: driver.lane_number)

    # Order other_drivers by completed_races only... once we've filled all the lanes
    #   we don't care if they are sitting out or not.
    drivers_not_racing.sort(key=lambda driver: driver.completed_races)

    #may need to convert drivers_not_racing into a list of DriverWithLane objects
    # drivers_not_racing = [DriverWithLane.create_from_driver(d) for d in drivers_not_racing]

    return NextRaceSetup(
        next_race_drivers=lanes_with_drivers,
        other_drivers=drivers_not_racing
    )
