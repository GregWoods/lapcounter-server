import json
from collections import defaultdict
from typing import Optional


def calculate_race_points(
    scoring_method: Optional[str],
    scoring_points_json: Optional[str],
    position: Optional[int],
) -> int:
    # Finishing Position races always score by position ('PositionPoints').
    # (The old 'LapPoints' concept has been removed.)
    if scoring_method != 'PositionPoints':
        return 0

    if position is None or not scoring_points_json:
        return 0
    table = json.loads(scoring_points_json)
    idx = position - 1
    return table[idx] if 0 <= idx < len(table) else 0


def session_points_rows(race_ids: list, driver_races: list, driver_names: dict,
                        scoring_method: Optional[str], scoring_points_json: Optional[str]) -> list:
    """A Points session's results table from the stored driver_races.position values.

    lapdata is the one authority on finishing position (#81) and the race_state
    subscriber stores what it published, lap penalties included, so nothing here ranks
    or subtracts anything: it only looks up points. A driver in a race with results but
    no position never started, and is listed under `dns`. A race with no stored results
    at all (its Finished race_state never reached the API) shows no positions."""
    positions = defaultdict(dict)
    dns = defaultdict(list)
    races_with_results = {dr.race_id for dr in driver_races if dr.position is not None}
    for dr in driver_races:
        if dr.position is not None:
            positions[dr.race_id][dr.driver_id] = dr.position
        elif dr.race_id in races_with_results:
            dns[dr.driver_id].append(str(dr.race_id))

    rows = []
    for did, name in driver_names.items():
        pos_map = {str(race_id): positions[race_id].get(did) for race_id in race_ids}
        pts_map = {key: calculate_race_points(scoring_method, scoring_points_json, pos)
                   for key, pos in pos_map.items()}
        rows.append({
            "driver_id": did, "driver_name": name,
            "positions": pos_map, "points": pts_map, "dns": dns[did],
            "total_points": sum(pts_map.values()),
            "races_entered": sum(1 for p in pos_map.values() if p is not None),
        })
    rows.sort(key=lambda d: (-d["total_points"], d["races_entered"]))
    return rows
