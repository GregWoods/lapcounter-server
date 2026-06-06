import json
import pytest
from points import calculate_race_points

F1 = json.dumps([25, 18, 15, 12, 10, 8, 6, 4, 2, 1])
CLUB = json.dumps([10, 8, 6, 5, 4, 3])


class TestPositionPoints:
    def test_p1_f1(self):
        assert calculate_race_points('PositionPoints', F1, 1, 20) == 25

    def test_p2_f1(self):
        assert calculate_race_points('PositionPoints', F1, 2, 20) == 18

    def test_p10_f1(self):
        assert calculate_race_points('PositionPoints', F1, 10, 20) == 1

    def test_position_beyond_table_scores_zero(self):
        assert calculate_race_points('PositionPoints', F1, 11, 20) == 0

    def test_dns_scores_zero(self):
        assert calculate_race_points('PositionPoints', F1, None, None) == 0

    def test_no_points_table_scores_zero(self):
        assert calculate_race_points('PositionPoints', None, 1, 20) == 0

    def test_empty_points_table_scores_zero(self):
        assert calculate_race_points('PositionPoints', '[]', 1, 20) == 0

    def test_p1_club(self):
        assert calculate_race_points('PositionPoints', CLUB, 1, 20) == 10

    def test_p3_club(self):
        assert calculate_race_points('PositionPoints', CLUB, 3, 20) == 6

    def test_p6_club(self):
        assert calculate_race_points('PositionPoints', CLUB, 6, 20) == 3

    def test_p7_club_beyond_table(self):
        assert calculate_race_points('PositionPoints', CLUB, 7, 20) == 0


class TestLapPoints:
    def test_laps_completed(self):
        assert calculate_race_points('LapPoints', None, 1, 15) == 15

    def test_zero_laps(self):
        assert calculate_race_points('LapPoints', None, 1, 0) == 0

    def test_dns_scores_zero(self):
        assert calculate_race_points('LapPoints', None, None, None) == 0

    def test_ignores_points_table(self):
        assert calculate_race_points('LapPoints', F1, 1, 12) == 12


class TestUnknownMethod:
    def test_unknown_method_scores_zero(self):
        assert calculate_race_points('FastestLap', F1, 1, 20) == 0

    def test_none_method_scores_zero(self):
        assert calculate_race_points(None, F1, 1, 20) == 0
