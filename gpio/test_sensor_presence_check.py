from sensor_presence_check import (DETECTABLE, INCONCLUSIVE, NOT_DRIVEN_HIGH, analyse,
                                   phantom_risk, summarise)


def pin(down, up, none=(0.5, 0)):
    return {"down": down, "up": up, "none": none}


def test_summarise_counts_high_fraction_and_level_changes():
    assert summarise([1, 1, 0, 0, 1]) == (0.6, 2)
    assert summarise([]) == (0.0, 0)


def test_a_board_that_drives_selected_high_is_detectable():
    plugged = pin(down=(1.0, 0), up=(1.0, 0))
    unplugged = pin(down=(0.0, 0), up=(1.0, 0))
    assert analyse(plugged, unplugged)[0] == DETECTABLE


def test_an_open_collector_board_looks_unplugged_under_pull_down():
    plugged = pin(down=(0.0, 0), up=(1.0, 0))
    unplugged = pin(down=(0.0, 0), up=(1.0, 0))
    assert analyse(plugged, unplugged)[0] == NOT_DRIVEN_HIGH


def test_a_car_crossing_mid_sample_is_inconclusive_not_detectable():
    plugged = pin(down=(0.97, 2), up=(0.97, 2))
    unplugged = pin(down=(0.0, 0), up=(1.0, 0))
    assert analyse(plugged, unplugged)[0] == INCONCLUSIVE


def test_floating_edges_are_counted_as_phantom_crossings():
    assert phantom_risk(pin(down=(0.0, 0), up=(1.0, 0), none=(0.4, 7))) == 4
    assert phantom_risk(pin(down=(0.0, 0), up=(1.0, 0), none=(0.0, 0))) == 0
