import pytest
from collections import Counter
from next_race import (
    assign_drivers_to_lanes,
    select_balanced_race_drivers,
    build_session_schedule,
)
from model import Lane, RaceSession
from responsemodel import DriverWithLane
from pprint import pprint


def make_session(races_per_driver=None):
    """A minimal in-memory RaceSession for the pure-logic scheduler tests."""
    return RaceSession(
        meeting_id=1, session_type='Points', end_condition='Laps',
        end_condition_info=20, races_per_driver=races_per_driver,
        scoring_method='PositionPoints',
    )


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

    #Check the driver names - to make sure we are not just using first_name, but the name which we will calculate
    assert result.lane_assignments[0].driver_name == "Driver BB"
    assert result.lane_assignments[1].driver_name == "Driver CC"
    assert result.lane_assignments[2].driver_name == "Driver FF"
    assert result.lane_assignments[3].driver_name == "Driver GG"
    assert result.lane_assignments[4].driver_name == "Driver HH"
    assert result.lane_assignments[5].driver_name == "Driver JJ"


# ── Disqualification (per-session sit-out limit) ──────────────────────

def test_disqualified_driver_excluded_from_lanes(test_lanes, test_drivers):
    """A disqualified driver is treated like sitting out: never assigned a lane, always
    pushed to other_drivers — even with a free lane available."""
    drivers = test_drivers[:6]
    drivers[2].disqualified = True  # Driver CC (id=3) is out of the session
    result = assign_drivers_to_lanes(drivers, test_lanes)

    assert all(d.id != 3 for d in result.lane_assignments), "Disqualified driver should not race"
    assert any(d.id == 3 for d in result.other_drivers), "Disqualified driver should be in other_drivers"
    # 5 remaining drivers fill 5 of the 6 lanes.
    assert_common_test_conditions(result, len(drivers), 5)


def test_disqualified_excluded_from_balanced_selection(test_lanes, test_drivers):
    """select_balanced_race_drivers ignores disqualified drivers when picking a race."""
    drivers = test_drivers[:6]
    for d in drivers:
        d.completed_races = 0
    drivers[0].disqualified = True  # id=1 out

    session = make_session(races_per_driver=2)
    selected, complete = select_balanced_race_drivers(session, drivers, test_lanes)

    assert not complete
    assert all(d.id != 1 for d in selected), "Disqualified driver must never be selected"


def test_schedule_refills_after_disqualification(test_lanes, test_drivers):
    """The user's scenario: with a driver removed from the session, the remaining schedule
    covers exactly the active drivers' outstanding races and never schedules the DQ'd one.
    6 drivers, target 2, all fresh, one DQ'd -> 5 drivers x 2 slots = 10 over 6 lanes =>
    two races of 5, and each active driver races exactly twice."""
    drivers = test_drivers[:6]
    for d in drivers:
        d.completed_races = 0
    drivers[0].disqualified = True  # id=1 out

    session = make_session(races_per_driver=2)
    schedule = build_session_schedule(session, drivers, test_lanes)

    scheduled_ids = [la.id for setup in schedule for la in setup.lane_assignments if la.id != 0]
    assert 1 not in scheduled_ids, "Disqualified driver must not appear in the schedule"

    appearances = Counter(scheduled_ids)
    active_ids = {d.id for d in drivers if not d.disqualified}
    assert set(appearances) == active_ids, "Every active driver should be scheduled"
    assert all(appearances[i] == 2 for i in active_ids), "Each active driver races exactly twice"
    assert len(schedule) == 2, "10 slots over 6 lanes should be two balanced races"


def test_disqualified_not_scheduled_even_when_under_target(test_lanes, test_drivers):
    """A DQ'd driver who is behind on races is still not given make-up races."""
    drivers = test_drivers[:6]
    for d in drivers:
        d.completed_races = 2
    drivers[0].disqualified = True
    drivers[0].completed_races = 0  # behind, but disqualified

    session = make_session(races_per_driver=3)
    schedule = build_session_schedule(session, drivers, test_lanes)

    scheduled_ids = [la.id for setup in schedule for la in setup.lane_assignments if la.id != 0]
    assert 1 not in scheduled_ids, "Disqualified driver gets no make-up races"


