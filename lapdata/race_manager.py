import math
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

from lap_clock import ClockAnchors, Crossing, RaceStart, interval_s

logger = logging.getLogger(__name__)

SUSPEND_AFTER = 12.0  # seconds before a driver is considered suspended

# What on_lap() made of a crossing it acted on. Published on driver_lap and stored in
# driver_laps.outcome, so every crossing that mattered can be traced after the meet (#86).
# Only COUNTED is a lap; the rest are void and carry no lap time.
CROSSING_COUNTED = 'counted'
CROSSING_START_LINE = 'start_line'   # the discarded part-lap from a grid behind the line
CROSSING_YELLOW_FLAG = 'yellow_flag'  # crossed after a yellow-flag grace expired
CROSSING_BASELINE = 'baseline'       # nothing to time it from: the next lap starts here
# ⚠️ An outcome says why a crossing did or didn't count, never what it cost. A yellow-flag
# crossing may or may not incur a lap penalty; penalties are a separate fact (race_penalties,
# and the driver_penalty topic in #88), not a kind of crossing (Greg, 2026-10-25).
CROSSING_OUTCOMES = (CROSSING_COUNTED, CROSSING_START_LINE, CROSSING_YELLOW_FLAG, CROSSING_BASELINE)


@dataclass
class DriverState:
    lane: int
    driver_id: int
    driver_name: str
    crossings: int = 0          # all S/F crossings including discarded start crossing
    # Lap penalties charged so far, in laps. Carried forward (Greg, 2026-10-25): a
    # penalty charged before the driver has laps to lose is still owed, so it is never
    # floored away. See laps_completed.
    penalty_laps: int = 0
    last_lap_time: float = 0.0
    best_lap_time: float = 999.999
    # The last crossing this driver made, as Layer 1 reported it — None until they
    # first cross. Held as a Crossing rather than a time so the NEXT lap can be a plain
    # counter subtraction on Layer 1's own clock, with no clock of ours involved.
    last_crossing: Optional[Crossing] = None
    # How last_lap_time was measured ('counter', 'from_go', 'anchored', 'arrival'),
    # carried through driver_lap as provenance. See lap_clock.
    last_lap_timing: str = ''
    finished: bool = False
    lap_times: list = field(default_factory=list)  # all real lap times in order
    # Whether this driver has already been charged the yellow-flag lap penalty for the
    # CURRENT incident — reset by yellow(), so a driver can only be penalized once per
    # incident even if they keep crossing during the same Paused window.
    yellow_penalty_applied: bool = False
    # Set the instant a penalty is applied, cleared on resume() — what the leaderboard's
    # instant "Penalty -N lap(s)" notice renders from.
    penalty_notice: Optional[dict] = None

    @property
    def has_started(self) -> bool:
        return self.crossings > 0

    @property
    def laps_completed(self) -> int:
        """Net laps: counted laps less lap penalties. The one rule for it — live, on
        recovery and in results (effective_laps_completed) — so they can't disagree (#86).

        ⚠️ Deliberately NOT floored at 0: it goes negative when a penalty lands before
        the driver has laps to lose, and that is what carries the penalty forward. The
        leaderboard shows laps *remaining*, which simply reads above the race length."""
        return len(self.lap_times) - self.penalty_laps


class RaceManager:

    def __init__(self, anchors: Optional[ClockAnchors] = None):
        # Injected so this module stays pure and DB-free: the anchors are fed from MQTT
        # by timestamps_to_lapdata, and tests drive them directly. Defaulted so a
        # RaceManager is still usable on its own.
        self.anchors = anchors if anchors is not None else ClockAnchors()
        # Lights-out on lapdata's monotonic clock, and where that sits on each Layer 1
        # clock. None until start(). Lap 1 is the only lap timed from it.
        self.race_start: Optional[RaceStart] = None
        # None until a lineup is loaded, and published as null in race_state. They are
        # identities, not counts: a 0 here is a race that doesn't exist, and every consumer
        # would have to know to treat it as falsy. RaceControl didn't, and rendered
        # "No race of 7" when lapdata started against an empty queue.
        self.race_id: Optional[int] = None
        self.race_number: Optional[int] = None
        self.target_laps: int = 0
        self.count_first_crossing: bool = False
        self.state: str = 'NotStarted'
        self.start_lights: int = 0  # 0-5 start lights lit during the ArmedForStart countdown
        self.race_start_time: Optional[float] = None
        self.race_fastest_lap: float = 999.999
        self.yellow_grace_seconds: float = 5.0
        self.min_lap_time: Optional[float] = None  # seconds; None = use lapdata's MINIMUM_LAP_TIME fallback
        # Whole seconds until a yellow flag's grace period cuts power; None outside
        # Yellow. Ticked down by lapdata's own timers, like start_lights, so a display
        # renders the number it's given instead of comparing a deadline against its
        # own clock — which on an old phone around the track can't be trusted.
        self.yellow_seconds_left: Optional[int] = None
        # % of full power the powerbase should be at right now (BLE only; GPIO can never
        # cut power so this is inert there). Resolved here, not inferred from `state` by
        # BLE, because only this class knows *why* a Paused race is Paused — a manual
        # immediate stop always means 0, but a yellow-grace expiry means whatever
        # yellow_post_grace_power_pct says. See CLAUDE.md "Yellow flags: power-based
        # handling".
        self.power_pct: int = 100
        self.yellow_grace_power_pct: int = 100
        self.yellow_post_grace_power_pct: int = 0
        # GPIO-only substitute deterrent for a yellow flag it can't actually enforce:
        # laps deducted from a driver who crosses the line after the grace period
        # expires. 0 = no penalty (the BLE default — power really was cut). Points
        # sessions only; see on_lap().
        self.yellow_lap_penalty_laps: int = 0
        # True only while Paused because a yellow-flag grace period expired — as
        # opposed to an immediate manual pause — since only that case is eligible for
        # the lap penalty above.
        self._paused_from_yellow_expiry: bool = False
        # Plain dicts describing a penalty just applied, drained and published as
        # `driver_penalty` by timestamps_to_lapdata's publish_pending_penalties() (#88) —
        # kept out of this pure, I/O-free class.
        self.pending_penalty_records: list = []
        self.drivers: Dict[int, DriverState] = {}  # keyed by lane number
        self.session_type: str = 'Points'
        self.race_duration_seconds: Optional[float] = None
        self.race_end_time: Optional[float] = None
        self.session_drivers: Dict[int, dict] = {}  # keyed by driver_id; FastestLap only
        # True once restore() has rebuilt this race from the DB after a restart; only
        # changes how a missing crossing baseline is logged.
        self.recovered: bool = False

    def load_lineup(self, race_id: int, race_number: int, target_laps: int,
                    lane_assignments: list, count_first_crossing: bool = False,
                    session_type: str = 'Points', race_duration_seconds=None,
                    session_drivers=None, yellow_grace_seconds: float = 5.0,
                    yellow_grace_power_pct: int = 100, yellow_post_grace_power_pct: int = 0,
                    yellow_lap_penalty_laps: int = 0,
                    min_lap_time: Optional[float] = None):
        """Load a pending race lineup. Call before start()."""
        self.race_id = race_id
        self.race_number = race_number
        self.count_first_crossing = count_first_crossing
        self.state = 'NotStarted'
        self.start_lights = 0
        self.race_start = None
        self.race_start_time = None
        self.race_end_time = None
        self.race_fastest_lap = 999.999
        self.session_type = session_type
        self.race_duration_seconds = race_duration_seconds
        self.yellow_grace_seconds = yellow_grace_seconds
        self.yellow_seconds_left = None
        self.power_pct = 100
        self.yellow_grace_power_pct = yellow_grace_power_pct
        self.yellow_post_grace_power_pct = yellow_post_grace_power_pct
        self.yellow_lap_penalty_laps = yellow_lap_penalty_laps
        self.min_lap_time = min_lap_time
        self._paused_from_yellow_expiry = False
        self.pending_penalty_records = []
        self.recovered = False

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

    def restore(self, started_at: Optional[float], laps: Dict[int, list], now: float,
                lap_penalties: Optional[Dict[int, int]] = None,
                crossings: Optional[Dict[int, int]] = None):
        """Rebuild a race that was Running when lapdata went away. Call after load_lineup().

        `laps` is driver_id -> that driver's counted lap times in order, from the DB,
        `lap_penalties` driver_id -> laps already deducted live (race_penalties), which
        driver_laps doesn't reflect, and `crossings` driver_id -> every crossing stored for
        them, void ones included (None from an API that predates it). That is all the DB
        can give back: the clock anchors
        and each car's last crossing were in memory only, so the next lap can't be timed.
        Hence:

        - the race comes back Paused with power at 0 — it can't be timed and the operator
          hasn't signed off on cars moving. Resume (or End) from Race Control.
        - each driver's first crossing after resume is only a new baseline, not a lap
          (see on_lap's no-baseline branch). The lap that straddled the restart is lost
          rather than guessed.
        - positions within a lap count fall back to lane order: the order of last
          crossings is gone.

        A timed race whose time ran out while we were away, or a Laps race where everyone
        had already taken the chequered flag, comes back Finished so the finish gets persisted.
        """
        self.recovered = True
        self.race_start_time = started_at
        if started_at is not None and self.race_duration_seconds:
            self.race_end_time = started_at + self.race_duration_seconds
        lap_penalties = lap_penalties or {}

        for driver in self.drivers.values():
            times = laps.get(driver.driver_id, [])
            driver.lap_times = [round(t, 3) for t in times]
            driver.penalty_laps = lap_penalties.get(driver.driver_id, 0)
            if crossings is not None:
                # Void crossings are in driver_laps too (#86), the start-line one included,
                # so whether a driver has started is a stored fact rather than a guess. A
                # car that never left the grid comes back not started, and can't hold the
                # race open. ⚠️ Only as good as dbwriter's record: a start-line driver_lap
                # it missed makes a racing driver look unstarted (#77).
                driver.crossings = max(crossings.get(driver.driver_id, 0), len(times))
            else:
                # An older API sends no crossing counts. With the grid behind the line the
                # start-line crossing did happen, but for a driver still on lap 1 there's no
                # telling whether it had. Assume it had: counting them as started only means
                # a car that truly never left holds the race open until the operator ends
                # it, where the other guess could end the race under a driver still racing.
                driver.crossings = len(times) + (0 if self.count_first_crossing else 1)
            if times:
                driver.last_lap_time = times[-1]
                driver.best_lap_time = min(times)
                self.race_fastest_lap = min(self.race_fastest_lap, driver.best_lap_time)
                if self.session_type == 'FastestLap':
                    for t in times:
                        self._update_session_fastest(driver.driver_id, driver.driver_name, t)

        if self.session_type != 'FastestLap':
            self._restore_chequered_flag(laps, lap_penalties)

        self.state = 'Paused'
        self.power_pct = 0
        self._paused_from_yellow_expiry = False
        counts = {d.lane: d.laps_completed for d in self.drivers.values()}
        logger.warning(f"Race {self.race_id} recovered from the database as Paused, laps by lane: {counts}")

        if self.race_end_time is not None and now >= self.race_end_time:
            self.end()
            logger.warning(f"Race {self.race_id} ran out of time while lapdata was away — finished")
        else:
            self._check_race_end()

    def _restore_chequered_flag(self, laps: Dict[int, list], lap_penalties: Dict[int, int]):
        """Re-mark who had taken the chequered flag. on_lap finishes a driver on reaching the
        target *or* on any counted lap after someone else has, so a count alone misses the
        second group. Lap 1 is timed from lights-out, so a driver's running total of lap
        times is the race time of each crossing — enough to say whose last counted lap came
        after the first finish.

        After a single restart this is exact: every counted lap is a counter subtraction,
        so the running totals are true race times.

        ⚠️ Not after a second restart in the same race. The lap that straddled the first
        one is missing from every driver's total, by a different amount for each (how far
        round the lap each car was), so a driver can land on the wrong side of the flag
        either way: wrongly finished, they stop counting and lose a lap; wrongly not, they
        must come back out after pulling in and gain one. Neither is safe — finishing
        position is laps first. Each crossing's clock and counter_ms are now in
        driver_laps (#27), so recovery could fix this by timing from those instead —
        it doesn't use them yet."""
        flag_at = None
        for driver in self.drivers.values():
            if driver.laps_completed >= self.target_laps:
                driver.finished = True
                times = laps.get(driver.driver_id, [])
                reached = sum(times[:self.target_laps + lap_penalties.get(driver.driver_id, 0)])
                flag_at = reached if flag_at is None else min(flag_at, reached)
        if flag_at is None:
            return
        for driver in self.drivers.values():
            times = laps.get(driver.driver_id, [])
            if times and sum(times) > flag_at:
                driver.finished = True

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
        self.start_lights = 0
        logger.info(f"Race {self.race_id} armed — awaiting lights-out timer")

    def abort_start(self):
        """Back to staged from the start lights: nothing has been timed yet, so the
        operator simply arms again. A Paused race needs a lights-out to resume from."""
        self.state = 'NotStarted'
        self.start_lights = 0
        self.power_pct = 100
        logger.info(f"Race {self.race_id} start aborted — staged again")

    def start(self, go_local: Optional[float] = None):
        """Lights out. `go_local` is that instant on lapdata's time.monotonic() clock,
        taken by the caller *before* it waited for any lock — it is the base every lap 1
        is timed from, so time spent blocking would land in lap 1.

        race_start_time (wall clock) survives for display, the time-expiry timer and the
        races.started_at the API stores from race_state. None of those needs to be better
        than roughly right, and
        none of them times a lap any more.
        """
        self.state = 'Running'
        self.start_lights = 0  # lights out
        self.power_pct = 100
        self.race_start = RaceStart(local=go_local if go_local is not None else time.monotonic())
        self.race_start_time = time.time()
        if self.race_duration_seconds:
            self.race_end_time = self.race_start_time + self.race_duration_seconds
        logger.info(f"Race {self.race_id} started — lights out at t={self.race_start_time:.3f}"
                    + (f", ends at t={self.race_end_time:.3f}" if self.race_end_time else ""))

    def yellow(self):
        """Yellow flag: cars keep racing at full power for yellow_grace_seconds (the
        caller is responsible for scheduling the timer that then calls pause()).

        ⚠️ Laps KEEP COUNTING through the grace period (Greg, 2026-09-20). The cars are
        still under power and still racing — that is the whole point of the grace, to let
        everyone finish the corner and get clear — so a crossing during it is a real lap
        and counting stops only when the power actually goes (pause()). Treating Yellow
        like Paused silently threw those laps away.

        See CLAUDE.md "Yellow flags: power-based handling"."""
        self.state = 'Yellow'
        self.yellow_seconds_left = math.ceil(self.yellow_grace_seconds)
        self.power_pct = self.yellow_grace_power_pct
        # A fresh incident: every driver is eligible for the lap penalty again if they
        # cross after this grace period expires.
        for driver in self.drivers.values():
            driver.yellow_penalty_applied = False
        logger.info(f"Race {self.race_id} yellow flag — power cuts in {self.yellow_grace_seconds:.1f}s")

    def pause(self, power_pct: int = 0, from_yellow_expiry: bool = False):
        """Stop the cars. `power_pct`/`from_yellow_expiry` distinguish *why*: an
        immediate manual pause (the defaults) is always a hard stop, never eligible for
        the lap penalty; a yellow-grace expiry passes the session's configured
        yellow_post_grace_power_pct and from_yellow_expiry=True, which is what on_lap()
        checks before applying a penalty."""
        self.state = 'Paused'
        self.yellow_seconds_left = None
        self.power_pct = power_pct
        self._paused_from_yellow_expiry = from_yellow_expiry
        logger.info(f"Race {self.race_id} paused (power {power_pct}%)")

    def resume(self):
        self.state = 'Running'
        self.yellow_seconds_left = None
        self.power_pct = 100
        self._paused_from_yellow_expiry = False
        for driver in self.drivers.values():
            driver.penalty_notice = None
        logger.info(f"Race {self.race_id} resumed")

    def end(self):
        self.state = 'Finished'
        self.yellow_seconds_left = None
        self.power_pct = 100
        self._paused_from_yellow_expiry = False
        logger.info(f"Race {self.race_id} ended by control signal")

    def race_time(self, driver: DriverState) -> float:
        """Seconds from lights-out to this driver's last crossing — what positions are
        sorted on within a lap count, and what the suspended check compares.

        On one clock this ranks cars by their raw counters exactly, so two cars crossing
        milliseconds apart can't be reordered by which notification we happened to get
        first."""
        if self.race_start is None or driver.last_crossing is None:
            return 0.0
        return self.race_start.since_go(driver.last_crossing, self.anchors)[0]

    def _apply_yellow_lap_penalty(self, driver: DriverState, crossing: Crossing):
        """GPIO-only substitute deterrent: it can't cut power, so a yellow-flag crossing
        costs the driver laps instead — once per incident, however often they cross.
        Points sessions only — a FastestLap lap made through a yellow flag is already
        effectively self-penalizing, since it will essentially never be a personal best.

        The record names the crossing that incurred it (clock + counter_ms, the same pair
        its driver_laps row carries), for traceability only: the penalty is its own fact
        and is never re-derived from the void crossing (#88)."""
        if (self.session_type == 'FastestLap' or self.yellow_lap_penalty_laps <= 0
                or driver.yellow_penalty_applied):
            return
        driver.yellow_penalty_applied = True
        driver.penalty_laps += self.yellow_lap_penalty_laps
        driver.penalty_notice = {'type': 'lap', 'amount': self.yellow_lap_penalty_laps}
        self._record_penalty(driver, 'lap', self.yellow_lap_penalty_laps,
                             'yellow_flag_grace_expired', crossing)
        logger.info(f"Lane {driver.lane} ({driver.driver_name}) crossed after the yellow-flag "
                    f"grace period — lap penalty applied, now {driver.laps_completed} laps")

    def _record_penalty(self, driver: DriverState, penalty_type: str, amount,
                        reason: str, crossing: Optional[Crossing] = None):
        """Queue a just-applied penalty for publishing as `driver_penalty`. Whatever
        triggered it, it gets its identity here, once (#94): `penalty_id` is the
        race_penalties dedup key, so a redelivery is dropped rather than charged twice,
        and `issued_at` is when it was given. Both are minted now and travel in the
        record, so republishing it can never mint new ones. `crossing` names the crossing
        that incurred it, if any (a marshal's penalty would have none)."""
        self.pending_penalty_records.append({
            'penalty_id': str(uuid.uuid4()), 'issued_at': time.time(),
            'driver_id': driver.driver_id, 'penalty_type': penalty_type,
            'amount': amount, 'reason': reason,
            'clock': crossing.clock if crossing else None,
            'counter_ms': crossing.counter_ms if crossing else None,
        })

    # States in which a crossing is a real lap: the cars are under power and racing.
    # Yellow is in here because its grace period keeps full power on — see yellow().
    COUNTING_STATES = ('Running', 'Yellow')

    def on_lap(self, lane: int, crossing: Crossing) -> Optional[str]:
        """
        Process a lap crossing. Returns what it was (one of CROSSING_OUTCOMES), which
        also means race state changed and should be published; or None if it was
        ignored — the cars aren't racing, the lane isn't in this race, or the driver has
        finished. The caller records the outcome as it is, rather than inferring it from
        how lap_times changed.
        """
        # A crossing after the yellow-flag grace period expired is void: the race is
        # stopped and nobody should be on the move. Gated on _paused_from_yellow_expiry
        # (not just state=='Paused') so a crossing under an immediate manual pause,
        # unrelated to a yellow flag, is still simply ignored.
        if self.state == 'Paused' and self._paused_from_yellow_expiry:
            driver = self.drivers.get(lane)
            if driver is None or driver.finished:
                return None
            # Counts as a crossing (so with the grid behind the line, a yellow-flag
            # crossing that was the car's first one is its start-line crossing too) but is
            # void for everything else (Greg, 2026-10-25): an existing last_crossing is
            # left alone, so the next lap is timed from the last counted crossing, or from
            # lights-out if there is none, and positions still sort on that counted
            # crossing. Only a driver with no crossing yet takes this one, as the
            # start-line crossing does — otherwise a car that has plainly started would
            # sort on a race time of 0.0 and could never be marked suspended.
            driver.crossings += 1
            if driver.last_crossing is None:
                driver.last_crossing = crossing
            self._apply_yellow_lap_penalty(driver, crossing)
            return CROSSING_YELLOW_FLAG

        if self.state not in self.COUNTING_STATES:
            return None

        driver = self.drivers.get(lane)
        if driver is None or driver.finished:
            return None

        driver.crossings += 1

        # Discard the first crossing when count_first_crossing is False.
        # This covers the case where the grid is just before the S/F line and the
        # car crosses almost immediately after lights out — not a real lap.
        if not self.count_first_crossing and driver.crossings == 1:
            driver.last_crossing = crossing  # preserves crossing order for position sort
            logger.info(f"Lane {lane}: start-line crossing discarded")
            return CROSSING_START_LINE

        # ⚠️ Lap 1 is timed from LIGHTS-OUT in every race, whatever the start grid
        # (Greg, 2026-09-20). The grid only decides which crossing *ends* lap 1: with the
        # grid in front of the line it is the first crossing, and with the grid behind it
        # the first crossing is a part-lap that is discarded, so lap 1 runs from
        # lights-out to the second. Either way the clock starts when the lights go out —
        # a driver's race begins there, not when they happen to reach the line.
        #
        # So lap 1 is the one lap in every race that has to cross from Layer 1's clock
        # onto ours, which is what layer1_clock (the heartbeat) exists for. Lap 2 onwards
        # is the interval from the previous counted crossing: a plain counter subtraction,
        # exact and anchor-free.
        #
        # "No laps yet" is lap_times, not laps_completed: laps_completed is net of lap
        # penalties and can be 0 or below after real laps, and the next lap must still be
        # timed from the previous counted crossing, not from lights-out again. A yellow-flag
        # crossing adds nothing to lap_times and never moves an existing last_crossing, so
        # it can't change which of the first two branches is taken. A driver with no
        # crossing at all (only after a recovery, when race_start is None) takes it as
        # their baseline instead of the next crossing.
        if not driver.lap_times and self.race_start is not None:
            lap_time, timing = self.race_start.since_go(crossing, self.anchors)
        elif driver.last_crossing is not None:
            lap_time, timing = interval_s(driver.last_crossing, crossing, self.anchors)
        else:
            # Running with no lights-out recorded and nothing to measure from. Reachable:
            # resume() sets Running without a start(), so a 'resume' sent to a freshly
            # started lapdata lands here. Take this crossing as a baseline rather than
            # inventing an interval — a fabricated 0.0 would win fastest lap outright and
            # stand for the whole session.
            driver.last_crossing = crossing
            if self.recovered:
                logger.info(f"Lane {lane}: first crossing since recovery — new baseline, not a lap")
            else:
                logger.error(f"Lane {lane} crossed while Running with no recorded lights-out "
                             f"(resumed without a start?) — using it as the lap 1 baseline")
            return CROSSING_BASELINE

        driver.last_lap_time = lap_time
        driver.last_lap_timing = timing
        driver.last_crossing = crossing
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
        return CROSSING_COUNTED

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
            # Reachable from Yellow, now that laps count through the grace period: the
            # last driver can take the chequered flag before the power cut. Leaving the
            # countdown set would publish a Finished race with a stale "Ns" on it.
            self.yellow_seconds_left = None
            self.power_pct = 100
            self._paused_from_yellow_expiry = False
            logger.info(f"Race {self.race_id} complete")

    def to_dict(self) -> dict:
        """Serialise to the race_state MQTT message format."""
        if self.session_type == 'FastestLap':
            return self._to_dict_fastest_lap()
        return self._to_dict_standard()

    def _to_dict_standard(self) -> dict:
        race_times = {d.lane: self.race_time(d) for d in self.drivers.values()}
        latest_race_time = max(race_times.values(), default=0.0)

        sorted_drivers = sorted(
            self.drivers.values(),
            key=lambda d: (-d.laps_completed, not d.has_started, race_times[d.lane]),
        )

        driver_list = []
        for position, driver in enumerate(sorted_drivers, start=1):
            rt = race_times[driver.lane]
            # Can exceed target_laps: a carried-forward penalty is laps still owed.
            laps_remaining = max(0, self.target_laps - driver.laps_completed)
            suspended = (
                driver.last_crossing is not None
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
                'penalty_notice': driver.penalty_notice,
            })

        # Sort by lane — React indexes drivers by lane number
        driver_list.sort(key=lambda d: d['lane'])

        return {
            'race_id': self.race_id,
            'race_number': self.race_number,
            'state': self.state,
            'start_lights': self.start_lights,
            'session_type': self.session_type,
            'target_laps': self.target_laps,
            'count_first_crossing': self.count_first_crossing,
            'race_fastest_lap': round(self.race_fastest_lap, 3) if self.race_fastest_lap < 999 else None,
            'race_start_time': self.race_start_time,
            'yellow_seconds_left': self.yellow_seconds_left,
            'power_pct': self.power_pct,
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
            'start_lights': self.start_lights,
            'session_type': 'FastestLap',
            'race_start_time': self.race_start_time,
            'race_end_time': self.race_end_time,
            'race_fastest_lap': round(self.race_fastest_lap, 3) if self.race_fastest_lap < 999 else None,
            'yellow_seconds_left': self.yellow_seconds_left,
            'power_pct': self.power_pct,
            'session_drivers': all_driver_data,
        }
