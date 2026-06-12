import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

logger = logging.getLogger(__name__)

SUSPEND_AFTER = 12.0  # seconds before a driver is considered suspended


@dataclass
class DriverState:
    lane: int
    driver_id: int
    driver_name: str
    crossings: int = 0          # all S/F crossings including discarded start crossing
    laps_completed: int = 0     # real completed laps
    last_lap_time: float = 0.0
    best_lap_time: float = 999.999
    last_crossing_time: float = 0.0   # time of last real lap crossing (0 = none yet)
    finished: bool = False
    lap_times: list = field(default_factory=list)  # all real lap times in order

    @property
    def has_started(self) -> bool:
        return self.crossings > 0

    def race_time(self, race_start_time: Optional[float]) -> float:
        if race_start_time is None or self.last_crossing_time == 0.0:
            return 0.0
        return self.last_crossing_time - race_start_time


class RaceManager:

    def __init__(self):
        self.race_id: int = 0
        self.race_number: int = 0
        self.target_laps: int = 0
        self.count_first_crossing: bool = False
        self.state: str = 'NotStarted'
        self.race_start_time: Optional[float] = None
        self.race_fastest_lap: float = 999.999
        self.drivers: Dict[int, DriverState] = {}  # keyed by lane number
        self.session_type: str = 'Points'
        self.race_duration_seconds: Optional[float] = None
        self.race_end_time: Optional[float] = None
        self.session_drivers: Dict[int, dict] = {}  # keyed by driver_id; FastestLap only

    def load_lineup(self, race_id: int, race_number: int, target_laps: int,
                    lane_assignments: list, count_first_crossing: bool = False,
                    session_type: str = 'Points', race_duration_seconds=None,
                    session_drivers=None):
        """Load a pending race lineup. Call before start()."""
        self.race_id = race_id
        self.race_number = race_number
        self.count_first_crossing = count_first_crossing
        self.state = 'NotStarted'
        self.race_start_time = None
        self.race_end_time = None
        self.race_fastest_lap = 999.999
        self.session_type = session_type
        self.race_duration_seconds = race_duration_seconds

        # FastestLap: time-limited, so target_laps is irrelevant
        self.target_laps = target_laps if session_type != 'FastestLap' else 9999

        self.drivers = {}
        for a in lane_assignments:
            if a.get('id', 0) == 0:
                continue  # empty lane slot
            lane = a['lane_number']
            self.drivers[lane] = DriverState(
                lane=lane,
                driver_id=a['id'],
                driver_name=a['driver_name'],
            )

        if session_type == 'FastestLap':
            self._merge_session_drivers(lane_assignments, session_drivers or [])

        logger.info(
            f"Loaded race {race_id} ({target_laps} laps/{race_duration_seconds}s, "
            f"{len(self.drivers)} drivers, session_type={session_type})"
        )

    def _merge_session_drivers(self, lane_assignments: list, session_drivers: list):
        """Merge API session driver list into in-memory session_drivers.

        Preserves existing in-memory fastest laps (accumulated across races in
        this session) while adding any newly encountered drivers from the API.
        Once the DB writer is implemented, the API will supply historical bests
        on LapData restart too.
        """
        for sd in session_drivers:
            driver_id = sd['driver_id'] if isinstance(sd, dict) else sd.driver_id
            driver_name = sd['driver_name'] if isinstance(sd, dict) else sd.driver_name
            db_best = (sd.get('session_fastest_lap') if isinstance(sd, dict)
                       else sd.session_fastest_lap)
            if driver_id not in self.session_drivers:
                self.session_drivers[driver_id] = {
                    'driver_id': driver_id,
                    'driver_name': driver_name,
                    'session_fastest_lap': db_best,
                }
            else:
                self.session_drivers[driver_id]['driver_name'] = driver_name
                mem_best = self.session_drivers[driver_id]['session_fastest_lap']
                if db_best is not None and (mem_best is None or db_best < mem_best):
                    self.session_drivers[driver_id]['session_fastest_lap'] = db_best

        # Ensure every current-race driver is in session_drivers
        for a in lane_assignments:
            driver_id = a.get('id', 0)
            if driver_id == 0:
                continue
            if driver_id not in self.session_drivers:
                self.session_drivers[driver_id] = {
                    'driver_id': driver_id,
                    'driver_name': a['driver_name'],
                    'session_fastest_lap': None,
                }

    def arm(self):
        self.state = 'ArmedForStart'
        logger.info(f"Race {self.race_id} armed — awaiting lights-out timer")

    def start(self):
        self.state = 'Running'
        self.race_start_time = time.time()
        if self.race_duration_seconds:
            self.race_end_time = self.race_start_time + self.race_duration_seconds
        logger.info(f"Race {self.race_id} started — lights out at t={self.race_start_time:.3f}"
                    + (f", ends at t={self.race_end_time:.3f}" if self.race_end_time else ""))

    def pause(self):
        self.state = 'Paused'
        logger.info(f"Race {self.race_id} paused")

    def resume(self):
        self.state = 'Running'
        logger.info(f"Race {self.race_id} resumed")

    def end(self):
        self.state = 'Finished'
        logger.info(f"Race {self.race_id} ended by control signal")

    def on_lap(self, lane: int, crossing_time: float) -> bool:
        """
        Process a lap crossing. Returns True if race state was updated (triggers publish).
        Ignores crossings when not Running, or from lanes not in this race.
        """
        if self.state != 'Running':
            return False

        driver = self.drivers.get(lane)
        if driver is None or driver.finished:
            return False

        driver.crossings += 1

        # Discard the first crossing when count_first_crossing is False.
        # This covers the case where the grid is just before the S/F line and the
        # car crosses almost immediately after lights out — not a real lap.
        if not self.count_first_crossing and driver.crossings == 1:
            driver.last_crossing_time = crossing_time  # preserves crossing order for position sort
            logger.info(f"Lane {lane}: start-line crossing discarded")
            return True

        # Real lap — lap 1 is always timed from race_start_time (lights out);
        # subsequent laps from the previous real crossing.
        if driver.laps_completed == 0:
            lap_time = crossing_time - self.race_start_time
        else:
            lap_time = crossing_time - driver.last_crossing_time

        driver.last_lap_time = lap_time
        driver.last_crossing_time = crossing_time
        driver.laps_completed += 1
        driver.lap_times.append(round(lap_time, 3))

        if lap_time < driver.best_lap_time:
            driver.best_lap_time = lap_time
        if lap_time < self.race_fastest_lap:
            self.race_fastest_lap = lap_time

        if self.session_type == 'FastestLap':
            self._update_session_fastest(driver.driver_id, driver.driver_name, lap_time)

        # Chequered flag: once any driver finishes, mark this driver finished on
        # their next crossing too (gives everyone one more lap after the winner).
        any_finished = any(d.finished for d in self.drivers.values())
        if driver.laps_completed >= self.target_laps or any_finished:
            driver.finished = True
            logger.info(f"Lane {lane} ({driver.driver_name}) finished — {driver.laps_completed} laps")

        self._check_race_end()
        return True

    def _update_session_fastest(self, driver_id: int, driver_name: str, lap_time: float):
        if driver_id not in self.session_drivers:
            self.session_drivers[driver_id] = {
                'driver_id': driver_id,
                'driver_name': driver_name,
                'session_fastest_lap': lap_time,
            }
        else:
            current = self.session_drivers[driver_id]['session_fastest_lap']
            if current is None or lap_time < current:
                self.session_drivers[driver_id]['session_fastest_lap'] = lap_time

    def _check_race_end(self):
        """Race ends when every driver has either finished or never crossed the start line."""
        if not any(d.finished for d in self.drivers.values()):
            return
        if all(d.finished or not d.has_started for d in self.drivers.values()):
            self.state = 'Finished'
            logger.info(f"Race {self.race_id} complete")

    def to_dict(self) -> dict:
        """Serialise to the race_state MQTT message format."""
        if self.session_type == 'FastestLap':
            return self._to_dict_fastest_lap()
        return self._to_dict_standard()

    def _to_dict_standard(self) -> dict:
        latest_race_time = max(
            (d.race_time(self.race_start_time) for d in self.drivers.values()),
            default=0.0,
        )

        sorted_drivers = sorted(
            self.drivers.values(),
            key=lambda d: (-d.laps_completed, not d.has_started, d.race_time(self.race_start_time)),
        )

        driver_list = []
        for position, driver in enumerate(sorted_drivers, start=1):
            rt = driver.race_time(self.race_start_time)
            laps_remaining = max(0, self.target_laps - driver.laps_completed)
            suspended = (
                driver.last_crossing_time > 0
                and not driver.finished
                and (rt + SUSPEND_AFTER) < latest_race_time
            )
            driver_list.append({
                'lane': driver.lane,
                'driver_id': driver.driver_id,
                'driver_name': driver.driver_name,
                'laps_completed': driver.laps_completed,
                'laps_remaining': laps_remaining,
                'last_lap': round(driver.last_lap_time, 3),
                'best_lap': round(driver.best_lap_time, 3) if driver.best_lap_time < 999 else None,
                'total_race_time': round(rt, 3),
                'position': position,
                'finished': driver.finished,
                'suspended': suspended,
                'has_started': driver.has_started,
                'is_race_fastest_lap': (
                    driver.best_lap_time < 999
                    and driver.best_lap_time == self.race_fastest_lap
                ),
            })

        # Sort by lane — React indexes drivers by lane number
        driver_list.sort(key=lambda d: d['lane'])

        return {
            'race_id': self.race_id,
            'race_number': self.race_number,
            'state': self.state,
            'session_type': self.session_type,
            'target_laps': self.target_laps,
            'count_first_crossing': self.count_first_crossing,
            'race_fastest_lap': round(self.race_fastest_lap, 3) if self.race_fastest_lap < 999 else None,
            'race_start_time': self.race_start_time,
            'drivers': driver_list,
        }

    def _to_dict_fastest_lap(self) -> dict:
        """Serialise to race_state for FastestLap sessions.

        All session drivers are included (not just current-race drivers) so React
        can render the full session leaderboard from a single MQTT message.
        """
        driver_by_id = {d.driver_id: d for d in self.drivers.values()}

        all_driver_data = []
        for driver_id, sd in self.session_drivers.items():
            driver = driver_by_id.get(driver_id)
            in_current_race = driver is not None
            lane = driver.lane if driver else None
            current_race_laps = list(reversed(driver.lap_times)) if driver else []

            all_driver_data.append({
                'driver_id': driver_id,
                'driver_name': sd['driver_name'],
                'session_fastest_lap': (
                    round(sd['session_fastest_lap'], 3)
                    if sd['session_fastest_lap'] is not None else None
                ),
                'in_current_race': in_current_race,
                'lane': lane,
                'current_race_laps': current_race_laps,
            })

        # Sort: fastest session lap ascending, nulls at end, then alphabetical
        all_driver_data.sort(key=lambda d: (
            d['session_fastest_lap'] is None,
            d['session_fastest_lap'] or 0,
            d['driver_name'],
        ))

        return {
            'race_id': self.race_id,
            'race_number': self.race_number,
            'state': self.state,
            'session_type': 'FastestLap',
            'race_start_time': self.race_start_time,
            'race_end_time': self.race_end_time,
            'race_fastest_lap': round(self.race_fastest_lap, 3) if self.race_fastest_lap < 999 else None,
            'session_drivers': all_driver_data,
        }
