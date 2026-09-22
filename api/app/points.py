import json
from typing import Optional


def calculate_race_points(
    scoring_method: Optional[str],
    scoring_points_json: Optional[str],
    position: Optional[int],
    laps_completed: Optional[int],
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
