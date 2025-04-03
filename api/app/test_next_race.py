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
        DriverWithLane(id=1, first_name='Driver A'),
        DriverWithLane(id=2, first_name='Driver B'),
        DriverWithLane(id=3, first_name='Driver C'),
        DriverWithLane(id=4, first_name='Driver D'),
        DriverWithLane(id=5, first_name='Driver E'),
        DriverWithLane(id=6, first_name='Driver F'),
        DriverWithLane(id=7, first_name='Driver G'),
        DriverWithLane(id=8, first_name='Driver H'),
        DriverWithLane(id=9, first_name='Driver J')
     ]


def test_only_one_driver_is_racing(test_lanes, test_drivers):
    drivers = test_drivers[:1]  # Only one driver racing
    result = assign_drivers_to_lanes(drivers, test_lanes)
    assert len(result.lane_assignments) == 6, "Should still return all 6 lanes"
    assert len([d for d in result.lane_assignments if d.id > 0]) == 1, "Only one driver should be racing"
    assert any(d.id == 1 for d in result.lane_assignments), "Driver A should be racing in one of the lanes"
    assert len(result.other_drivers) == 0, "No drivers should be sitting out"


def test_one_racing_one_sitting_out(test_lanes, test_drivers):
    drivers = test_drivers[:2]  # Only 2 drivers racing
    drivers[1].sit_out_next_race = True  # Mark the second driver as sitting out
    result = assign_drivers_to_lanes(drivers, test_lanes)
    pprint(result)
    assert len(result.lane_assignments) == 6, "Should still return all 6 lanes"
    assert len([d for d in result.lane_assignments if d.id > 0]) == 1, "Only one driver should be racing"
    assert any(d.id == 1 for d in result.lane_assignments), "Driver A should be racing in one of the lanes"
    assert len(result.other_drivers) == 1, "One driver should be sitting out"
    assert result.other_drivers[0].id == 2, "Driver B should be sitting out"