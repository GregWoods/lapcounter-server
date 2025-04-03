from fastapi.testclient import TestClient
from next_race import assign_drivers_to_lanes
from model import Lane
from responsemodel import DriverWithLane


def test_only_one_driver_is_racing():
    drivers = [
        DriverWithLane(id=1, first_name="Driver A", sit_out_next_race=False)
    ]

    lanes = [
        Lane(lane_number=1, color="Red", enabled=True),
        Lane(lane_number=2, color="Blue", enabled=True),
        Lane(lane_number=3, color="Green", enabled=False)  # Disabled lane
    ]
    
    result = assign_drivers_to_lanes(drivers, lanes)

    assert len(result.next_race_drivers) == 3, "Should have 3 lane positions (2 enabled + 1 disabled)"
    assert len([d for d in result.next_race_drivers if d.id > 0]) == 1, "Only one real driver should be racing"
    assert result.next_race_drivers[0].id == 0, "Driver A should be racing"
    assert len(result.other_drivers) == 0, "No drivers should be sitting out"
