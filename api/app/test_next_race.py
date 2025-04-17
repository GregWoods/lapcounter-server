import pytest
from next_race import assign_drivers_to_lanes
from model import Lane
from responsemodel import DriverWithLane
from pprint import pprint


@pytest.fixture
def test_lanes():
    
    return [
        Lane(lane_number=1, color='red', enabled=True),
        Lane(lane_number=2, color='green', enabled=True),
        Lane(lane_number=3, color='blue', enabled=True),
        Lane(lane_number=4, color='yellow', enabled=True),
        Lane(lane_number=5, color='orange', enabled=True),
        Lane(lane_number=6, color="white", enabled=True)
    ]

@pytest.fixture
def test_drivers():
     return[
        DriverWithLane(id=1, driver_name='Driver AA', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=2, driver_name='Driver BB', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=3, driver_name='Driver CC', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=4, driver_name='Driver DD', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=5, driver_name='Driver EE', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=6, driver_name='Driver FF', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=7, driver_name='Driver GG', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=8, driver_name='Driver HH', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3),
        DriverWithLane(id=9, driver_name='Driver JJ', completed_races=18, lane1_count=3, lane2_count=3, lane3_count=3, lane4_count=3, lane5_count=3, lane6_count=3)
     ]


def assert_common_test_conditions(result, expected_drivers_count, expected_racing_count):
    """
    Common assertions used across multiple tests
    
    Args:
        result: The NextRaceSetup result to test
        expected_drivers_count: Total number of drivers that should be accounted for
        expected_racing_count: Number of drivers expected to be racing
    """
    racing_drivers_count = len([d for d in result.lane_assignments if d.id > 0])
    assert expected_drivers_count == racing_drivers_count + len(result.other_drivers), "All drivers should be accounted for"
    assert len(result.lane_assignments) == 6, "Should still return all 6 lanes"
    assert racing_drivers_count == expected_racing_count, f"Should have {expected_racing_count} drivers racing"



def test_only_one_driver_is_racing(test_lanes, test_drivers):
    drivers = test_drivers[:1]  # Only one driver racing
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 1)
    assert any(d.id == 1 for d in result.lane_assignments), "Driver A should be racing in one of the lanes"
    assert len(result.other_drivers) == 0, "No drivers should be not racing"


def test_one_racing_one_sitting_out(test_lanes, test_drivers):
    drivers = test_drivers[:2]  # Only 2 drivers racing
    drivers[1].sit_out_next_race = True  # Mark the second driver as sitting out
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 1)
    pprint(result)
    assert any(d.id == 1 for d in result.lane_assignments), "Driver A should be racing in one of the lanes"
    assert result.other_drivers[0].id == 2, "Driver B should be not racing (sitting out)"


def test_prioritise_less_completed_races(test_lanes, test_drivers):
    drivers = list(test_drivers)    #create a copy
    # 4 drivers have raced more frequently than the 18 average, but one of them will still need to race to fill the lanes
    drivers[0].completed_races = 20     # Driver A, id=1
    drivers[2].completed_races = 20     # Driver C, id=3
    drivers[4].completed_races = 20     # Driver E, id=5
    drivers[6].completed_races = 20     # Driver G, id=7
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 6)

    potentially_racing_ids = {1, 3, 5, 7}       # Drivers A, C, E, G
    definitely_racing_ids = {2, 4, 6, 8, 9}     # all those who only raced 18 races
    all_possible_racing_ids = potentially_racing_ids | definitely_racing_ids

    # Check all other_drivers are in the set of all possible racing IDs
    assert all(d.id in all_possible_racing_ids for d in result.lane_assignments), "Only expected drivers should be racing"
    
    # Check that every ID in definitely_racing_ids is present in result.lane_assignments
    assert all(id in {d.id for d in result.lane_assignments} for id in definitely_racing_ids), "Some drivers will definitely be racing"



def test_all_drivers_sitting_out(test_lanes, test_drivers):
    # Create a copy of test_drivers
    drivers = list(test_drivers)
    
    # Set all drivers to sit out next race
    for driver in drivers:
        driver.sit_out_next_race = True
        
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 0)
    
    assert all(d.id == 0 for d in result.lane_assignments), "All lanes should have empty drivers"
    
    driver_ids = {d.id for d in drivers}
    other_driver_ids = {d.id for d in result.other_drivers}
    assert driver_ids == other_driver_ids, "All drivers should be in other_drivers"

    assert all(d.sit_out_next_race for d in result.other_drivers), "All other drivers should have sit_out_next_race=True"


# all lanes disabled
def test_all_lanes_disabled(test_lanes, test_drivers):
    drivers = list(test_drivers)
    
    for lane in test_lanes:
        lane.enabled = False
        
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 0)
    
    assert all(d.id == 0 for d in result.lane_assignments), "All lanes should have empty drivers"
    
    driver_ids = {d.id for d in drivers}
    other_driver_ids = {d.id for d in result.other_drivers}
    assert driver_ids == other_driver_ids, "All drivers should be in other_drivers"


# individual lanes disabled
def test_single_lane_disabled(test_lanes, test_drivers):
    drivers = list(test_drivers)
    
    # Disable lane 1
    test_lanes[0].enabled = False
    
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 5)

    pprint(result.lane_assignments)

    # Check that lane 1 is empty
    assert all(d.id == 0 for d in result.lane_assignments if d.lane_number == 1), "Lane 1 should have empty driver"


def test_lane_preference(test_lanes, test_drivers):
    drivers = list(test_drivers)

    # Set lane preferences for each driver
    drivers[1].lane1_count = 0  # Driver B prefers lane 1
    drivers[2].lane2_count = 0  # Driver C prefers lane 2
    drivers[5].lane3_count = 0  # Driver F prefers lane 3
    drivers[6].lane4_count = 0  # Driver G prefers lane 4
    drivers[7].lane5_count = 0  # Driver H prefers lane 5
    drivers[8].lane6_count = 0  # Driver J prefers lane 6

    # And ensure those drivers get picked first
    drivers[1].completed_races = 16
    drivers[2].completed_races = 16
    drivers[5].completed_races = 16
    drivers[6].completed_races = 16
    drivers[7].completed_races = 16
    drivers[8].completed_races = 16

    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert_common_test_conditions(result, len(drivers), 6)

    # Check that each driver is in their preferred lane
    assert result.lane_assignments[0].id == 2, "Driver B should be in lane 1"
    assert result.lane_assignments[1].id == 3, "Driver C should be in lane 2"
    assert result.lane_assignments[2].id == 6, "Driver F should be in lane 3"
    assert result.lane_assignments[3].id == 7, "Driver G should be in lane 4"
    assert result.lane_assignments[4].id == 8, "Driver H should be in lane 5"
    assert result.lane_assignments[5].id == 9, "Driver J should be in lane 6"

    #Check the driver names - to make sure names are taken from meeting_driver not driver
    assert result.lane_assignments[0].driver_name == "Driver BB"
    assert result.lane_assignments[1].driver_name == "Driver CC"
    assert result.lane_assignments[2].driver_name == "Driver FF"
    assert result.lane_assignments[3].driver_name == "Driver GG"
    assert result.lane_assignments[4].driver_name == "Driver HH"
    assert result.lane_assignments[5].driver_name == "Driver JJ"


