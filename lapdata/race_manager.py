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
    crossings: int = 0          # 0=not started, 1=Lap0, 2=Lap1 (first real lap), etc.
    last_lap_time: float = 0.0
    best_lap_time: float = 999.999
    last_crossing_time: float = 0.0
    finished: bool = False

    @property
    def laps_completed(self) -> int:
        # Lap 0 is the start-line crossing, not a real lap.
        # Lap 1 is the first real lap (crossings == 2).
        return max(0, self.crossings - 1)

    @property
    def has_started(self) -> bool:
        return self.crossings > 0

    def race_time(self, race_start_time: Optional[float]) -> float:
        if not self.has_started or race_start_time is None:
            return 0.0
        return self.last_crossing_time - race_start_time


class RaceManager:

    def __init__(self):
        self.race_id: int = 0
        self.target_laps: int = 0
        self.state: str = 'NotStarted'
        self.race_start_time: Optional[float] = None
        self.first_car_crossed: bool = False
        self.race_fastest_lap: float = 999.999
        self.drivers: Dict[int, DriverState] = {}  # keyed by lane number

    def load_lineup(self, race_id: int, target_laps: int, lane_assignments: list):
        """Load a pending race lineup. Call before start()."""
        self.race_id = race_id
        self.target_laps = target_laps
        self.state = 'NotStarted'
        self.race_start_time = None
        self.first_car_crossed = False
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
        logger.info(f"Loaded race {race_id} ({target_laps} laps, {len(self.drivers)} drivers)")

    def start(self):
        self.state = 'Running'
        logger.info(f"Race {self.race_id} started")

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

        # First car to cross after lights out — establishes the race clock
        if not self.first_car_crossed:
            self.race_start_time = crossing_time
            self.first_car_crossed = True
            driver.last_lap_time = 0.0
            driver.last_crossing_time = crossing_time
            logger.info(f"Race clock started: lane {lane} at t={crossing_time:.3f}")
            return True

        # Lap 0 for all other drivers — their first crossing, not a timed lap
        if driver.laps_completed == 0:
            driver.last_lap_time = 0.0
            driver.last_crossing_time = crossing_time
            return True

        # Real lap (lap 1+)
        # Lap 1 is timed from race_start_time; subsequent laps from last crossing
        last_time = self.race_start_time if driver.laps_completed == 1 else driver.last_crossing_time
        lap_time = crossing_time - last_time
        driver.last_lap_time = lap_time
        driver.last_crossing_time = crossing_time

        if lap_time < driver.best_lap_time:
            driver.best_lap_time = lap_time
        if lap_time < self.race_fastest_lap:
            self.race_fastest_lap = lap_time

        # Chequered flag: once any driver finishes, mark this driver finished too
        any_finished = any(d.finished for d in self.drivers.values())
        laps_remaining = max(0, self.target_laps - driver.laps_completed)
        if laps_remaining == 0 or any_finished:
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
            key=lambda d: (-d.laps_completed, d.race_time(self.race_start_time)),
        )

        driver_list = []
        for position, driver in enumerate(sorted_drivers, start=1):
            rt = driver.race_time(self.race_start_time)
            laps_remaining = max(0, self.target_laps - driver.laps_completed)
            suspended = (
                driver.has_started
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
            'state': self.state,
            'target_laps': self.target_laps,
            'race_fastest_lap': round(self.race_fastest_lap, 3) if self.race_fastest_lap < 999 else None,
            'race_start_time': self.race_start_time,
            'drivers': driver_list,
        }
