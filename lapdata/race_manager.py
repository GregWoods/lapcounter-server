import time
import logging
from dataclasses import dataclass
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

    def load_lineup(self, race_id: int, race_number: int, target_laps: int,
                    lane_assignments: list, count_first_crossing: bool = False):
        """Load a pending race lineup. Call before start()."""
        self.race_id = race_id
        self.race_number = race_number
        self.target_laps = target_laps
        self.count_first_crossing = count_first_crossing
        self.state = 'NotStarted'
        self.race_start_time = None
        self.race_fastest_lap = 999.999
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
        logger.info(
            f"Loaded race {race_id} ({target_laps} laps, {len(self.drivers)} drivers, "
            f"count_first_crossing={count_first_crossing})"
        )

    def arm(self):
        self.state = 'ArmedForStart'
        logger.info(f"Race {self.race_id} armed — awaiting lights-out timer")

    def start(self):
        self.state = 'Running'
        self.race_start_time = time.time()
        logger.info(f"Race {self.race_id} started — lights out at t={self.race_start_time:.3f}")

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

        if lap_time < driver.best_lap_time:
            driver.best_lap_time = lap_time
        if lap_time < self.race_fastest_lap:
            self.race_fastest_lap = lap_time

        # Chequered flag: once any driver finishes, mark this driver finished on
        # their next crossing too (gives everyone one more lap after the winner).
        any_finished = any(d.finished for d in self.drivers.values())
        if driver.laps_completed >= self.target_laps or any_finished:
            driver.finished = True
            logger.info(f"Lane {lane} ({driver.driver_name}) finished — {driver.laps_completed} laps")

        self._check_race_end()
        return True

    def _check_race_end(self):
        """Race ends when every driver has either finished or never crossed the start line."""
        if not any(d.finished for d in self.drivers.values()):
            return
        if all(d.finished or not d.has_started for d in self.drivers.values()):
            self.state = 'Finished'
            logger.info(f"Race {self.race_id} complete")

    def to_dict(self) -> dict:
        """Serialise to the race_state MQTT message format."""
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
            'target_laps': self.target_laps,
            'count_first_crossing': self.count_first_crossing,
            'race_fastest_lap': round(self.race_fastest_lap, 3) if self.race_fastest_lap < 999 else None,
            'race_start_time': self.race_start_time,
            'drivers': driver_list,
        }
