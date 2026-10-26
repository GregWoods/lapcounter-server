import json
from types import SimpleNamespace

import pytest
from points import calculate_race_points, session_points_rows

F1 = json.dumps([25, 18, 15, 12, 10, 8, 6, 4, 2, 1])
CLUB = json.dumps([10, 8, 6, 5, 4, 3])


class TestPositionPoints:
    def test_p1_f1(self):
        assert calculate_race_points('PositionPoints', F1, 1) == 25

    def test_p2_f1(self):
        assert calculate_race_points('PositionPoints', F1, 2) == 18

    def test_p10_f1(self):
        assert calculate_race_points('PositionPoints', F1, 10) == 1

    def test_position_beyond_table_scores_zero(self):
        assert calculate_race_points('PositionPoints', F1, 11) == 0

    def test_dns_scores_zero(self):
        assert calculate_race_points('PositionPoints', F1, None) == 0

    def test_no_points_table_scores_zero(self):
        assert calculate_race_points('PositionPoints', None, 1) == 0

    def test_empty_points_table_scores_zero(self):
        assert calculate_race_points('PositionPoints', '[]', 1) == 0

    def test_p1_club(self):
        assert calculate_race_points('PositionPoints', CLUB, 1) == 10

    def test_p3_club(self):
        assert calculate_race_points('PositionPoints', CLUB, 3) == 6

    def test_p6_club(self):
        assert calculate_race_points('PositionPoints', CLUB, 6) == 3

    def test_p7_club_beyond_table(self):
        assert calculate_race_points('PositionPoints', CLUB, 7) == 0


class TestUnknownMethod:
    def test_removed_lappoints_scores_zero(self):
        # 'LapPoints' was removed — only 'PositionPoints' scores now.
        assert calculate_race_points('LapPoints', None, 1) == 0

    def test_fastestlap_method_scores_zero(self):
        assert calculate_race_points('FastestLap', F1, 1) == 0

    def test_none_method_scores_zero(self):
        assert calculate_race_points(None, F1, 1) == 0


def dr(race_id, driver_id, position, laps_completed=10, fastest_lap_time=5.0):
    return SimpleNamespace(race_id=race_id, driver_id=driver_id, position=position,
                           laps_completed=laps_completed, fastest_lap_time=fastest_lap_time)


NAMES = {1: 'Ann', 2: 'Bob', 3: 'Cat'}


class TestSessionPointsRows:
    def test_stored_positions_are_used_without_re_ranking(self):
        """Bob is stored P1 with fewer raw laps and a slower fastest lap — a penalty
        or race time put him there, and the Results page must agree (#81)."""
        rows = session_points_rows(
            [7], [dr(7, 1, 2, laps_completed=10, fastest_lap_time=4.0),
                  dr(7, 2, 1, laps_completed=9, fastest_lap_time=5.0)],
            {1: 'Ann', 2: 'Bob'}, 'PositionPoints', CLUB)
        by_id = {r['driver_id']: r for r in rows}
        assert by_id[2]['positions'] == {'7': 1} and by_id[2]['total_points'] == 10
        assert by_id[1]['positions'] == {'7': 2} and by_id[1]['total_points'] == 8
        assert [r['driver_id'] for r in rows] == [2, 1]

    def test_a_non_starter_is_dns_and_scores_nothing(self):
        rows = session_points_rows([7], [dr(7, 1, 1), dr(7, 2, None)], NAMES, 'PositionPoints', CLUB)
        bob = next(r for r in rows if r['driver_id'] == 2)
        assert bob['dns'] == ['7']
        assert bob['positions'] == {'7': None}
        assert bob['total_points'] == 0 and bob['races_entered'] == 0

    def test_a_race_with_no_stored_results_is_not_dns(self):
        """Its Finished race_state never reached the API: unknown, not a non-start."""
        rows = session_points_rows([7], [dr(7, 1, None), dr(7, 2, None)], NAMES, 'PositionPoints', CLUB)
        assert all(r['dns'] == [] and r['total_points'] == 0 for r in rows)

    def test_points_add_up_across_races(self):
        rows = session_points_rows(
            [7, 8], [dr(7, 1, 1), dr(7, 2, 2), dr(8, 1, 2), dr(8, 2, 1), dr(8, 3, 3)],
            NAMES, 'PositionPoints', CLUB)
        by_id = {r['driver_id']: r for r in rows}
        assert by_id[1]['total_points'] == 18 and by_id[2]['total_points'] == 18
        assert by_id[3]['total_points'] == 6 and by_id[3]['races_entered'] == 1
