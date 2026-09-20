"""Correlating Layer 1's own counter with lapdata's clock.

Lap times must come from differences between Layer 1's own timestamps, never from a
conversion to lapdata's clock where that can be avoided. See docs/lap-timing-clocks.md
for why, and docs/lap-timing-plan.md for the design this implements.

A Layer 1 publishes `(clock, counter_ms)` pairs — on `car_timestamp` for a crossing, and
on `layer1_clock` as a bare heartbeat. The contract is:

1. Within one `clock`, `counter_ms` advances at real-time rate.
2. Layer 1 starts a new `clock` whenever that stops being true, or might have.
3. A `clock` value is never reused, across container restarts included.
4. lapdata only ever compares `clock` values for equality, and never parses them.

So two crossings on the same clock subtract exactly, with no clock of ours involved —
which is every lap but the first. Lap 1 is timed from lights-out, which is lapdata's own
timer, so that one lap needs the anchor below.

This module is pure: no MQTT, no wall clock, no race state. Everything is in lapdata's
`time.monotonic()` seconds, which is why setting the Pi's clock mid-meet (no RTC; set by
hand before a meet) can no longer affect any lap.
"""
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# How many clocks to keep anchors for. A lap that spans a clock change still has to
# convert its older end, and a yellow flag's halt-then-resume burns two at a time, so
# this is deliberately more than the one or two in play.
MAX_TRACKED_CLOCKS = 8

# A forward step in lapdata's own clock used to be possible (the Pi's clock being set,
# or a Docker VM catching up after the host slept) and dragged every later sample up
# without a running minimum ever following. time.monotonic() removes that cause, so what
# survives here is a guard against a Layer 1 that broke its counter without changing
# clock — exactly the bug the contract exists to prevent, hence the ERROR log.
#
# A normal sample only exceeds the true offset by its reporting delay: at most one
# round-robin rotation for BLE (one Slot packet per car ID, all 6 in turn). The first
# hardware run (2026-09-18, Pi Zero 2 W) measured ~1.8s for that, so 3s clears it but
# ~2x would be 3.6s — don't lower it without a rotation measured on the meet's hardware.
# The confirmation period matters too: a BLE stall delivers a late burst and then prompt
# samples again, and re-anchoring on the burst alone would stamp crossings late until a
# prompt sample dragged the anchor back.
CLOCK_STEP_THRESHOLD_S = 3.0
CLOCK_STEP_CONFIRM_S = 5.0

# What produced a lap time, carried through driver_lap for provenance.
TIMING_COUNTER = 'counter'      # both ends on one clock — exact, no anchor involved
TIMING_ANCHORED = 'anchored'    # ends on different clocks, converted through anchors
TIMING_FROM_GO = 'from_go'      # lap 1, from lights-out converted onto the crossing's clock
TIMING_ARRIVAL = 'arrival'      # last resort: no usable anchor, so MQTT arrival times


@dataclass(frozen=True)
class Crossing:
    """One start/finish crossing as Layer 1 reported it, plus when we heard about it.

    `arrival` is lapdata's `time.monotonic()` at the moment the message arrived, stamped
    before anything that could block. It is only ever used to anchor `counter_ms` to our
    clock (and as a last-resort fallback) — never as the crossing time itself, which is
    what `counter_ms` is for.
    """
    clock: str
    counter_ms: int
    arrival: float

    @property
    def counter_s(self) -> float:
        return self.counter_ms / 1000.0


class _Anchor:
    """The running minimum of (arrival - counter_s) for one clock, plus the divergence
    guard's state."""

    __slots__ = ('offset', 'run_since', 'run_min')

    def __init__(self, offset: float):
        self.offset = offset
        self.run_since: Optional[float] = None
        self.run_min: Optional[float] = None


class ClockAnchors:
    """Maps each Layer 1 clock onto lapdata's monotonic clock.

    Every sample is the true offset plus some transport delay, and delay is never
    negative, so the smallest `arrival - counter_s` seen is the best estimate of the
    offset, and it converges within a few samples. Under plan A the BLE Layer 1 feeds
    this from the Throttle characteristic at ~3.3 samples/s with a median lateness of
    1ms, so the anchor is essentially exact by lights-out — which is the whole point,
    since lap 1 is the one lap that depends on it.

    Thread-safe: lapdata's timer threads read it while paho's thread writes.
    """

    def __init__(self, max_clocks: int = MAX_TRACKED_CLOCKS):
        self._max_clocks = max_clocks
        self._anchors: Dict[str, _Anchor] = {}
        self._lock = threading.Lock()

    def observe(self, clock: str, counter_ms: int, arrival: float) -> None:
        """Feed one (clock, counter) sample seen at `arrival` (time.monotonic())."""
        candidate = arrival - counter_ms / 1000.0
        with self._lock:
            anchor = self._anchors.get(clock)
            if anchor is None:
                self._anchors[clock] = _Anchor(candidate)
                self._evict_locked()
                return

            # Keep insertion order fresh, so the clock in active use is never the one
            # evicted: dicts preserve insertion order, and re-inserting moves it to the end.
            del self._anchors[clock]
            self._anchors[clock] = anchor

            if candidate < anchor.offset:
                anchor.offset = candidate
                anchor.run_since = anchor.run_min = None
                return

            if candidate - anchor.offset <= CLOCK_STEP_THRESHOLD_S:
                anchor.run_since = anchor.run_min = None
                return

            if anchor.run_since is None:
                anchor.run_since, anchor.run_min = arrival, candidate
            else:
                anchor.run_min = min(anchor.run_min, candidate)
            if arrival - anchor.run_since >= CLOCK_STEP_CONFIRM_S:
                logger.error(
                    f"Clock {clock!r} has drifted {anchor.run_min - anchor.offset:.1f}s from its "
                    f"anchor for {CLOCK_STEP_CONFIRM_S:.0f}s — a Layer 1 broke its counter "
                    f"without starting a new clock. Re-anchoring."
                )
                anchor.offset = anchor.run_min
                anchor.run_since = anchor.run_min = None

    def _evict_locked(self):
        while len(self._anchors) > self._max_clocks:
            del self._anchors[next(iter(self._anchors))]

    def offset(self, clock: str) -> Optional[float]:
        with self._lock:
            anchor = self._anchors.get(clock)
            return anchor.offset if anchor else None

    def to_local(self, clock: str, counter_ms: float) -> Optional[float]:
        """That counter value as a lapdata time.monotonic() value, or None if this clock
        has no anchor (never seen, or evicted)."""
        offset = self.offset(clock)
        return None if offset is None else counter_ms / 1000.0 + offset

    def to_counter_ms(self, clock: str, local: float) -> Optional[float]:
        """A lapdata time.monotonic() value as a counter reading on that clock."""
        offset = self.offset(clock)
        return None if offset is None else (local - offset) * 1000.0


def interval_s(a: Crossing, b: Crossing, anchors: ClockAnchors) -> Tuple[float, str]:
    """Seconds from crossing `a` to crossing `b`, and how it was measured.

    Same clock is the normal case and is exact: a plain counter subtraction, with no
    clock of lapdata's involved however jittery the two arrivals were. Different clocks
    (a lap spanning a yellow-flag halt or a reconnect) converts both ends through their
    anchors, which is the least accurate path, and falls back to arrival times only if
    an anchor is missing entirely.
    """
    if a.clock == b.clock:
        return (b.counter_ms - a.counter_ms) / 1000.0, TIMING_COUNTER

    a_local = anchors.to_local(a.clock, a.counter_ms)
    b_local = anchors.to_local(b.clock, b.counter_ms)
    if a_local is not None and b_local is not None:
        return b_local - a_local, TIMING_ANCHORED

    logger.warning(
        f"No anchor for clock {a.clock!r} or {b.clock!r} — falling back to arrival times"
    )
    return b.arrival - a.arrival, TIMING_ARRIVAL


@dataclass
class RaceStart:
    """Lights-out, and where it sits on each Layer 1 clock.

    `local` is lapdata's own `time.monotonic()` at the instant the start-light sequence
    fired — the only definition of "go" there is, since no Layer 1 is told about it.

    The per-clock counter value is computed from the anchor the *first* time any car
    needs it, then frozen for the rest of the race. That matters: every car on one clock
    then shares a single correlation error, so it can shift lap 1's absolute value but
    can never reorder lap 1 times or positions. Computing it per car instead would let an
    anchor that improved between two cars' crossings change their relative lap 1s.
    """
    local: float
    counter_ms: Dict[str, float] = field(default_factory=dict)

    def counter_for(self, clock: str, anchors: ClockAnchors) -> Optional[float]:
        """Go, as a counter reading on `clock` — frozen on first use."""
        if clock not in self.counter_ms:
            counter = anchors.to_counter_ms(clock, self.local)
            if counter is None:
                return None
            self.counter_ms[clock] = counter
        return self.counter_ms[clock]

    def since_go(self, crossing: Crossing, anchors: ClockAnchors) -> Tuple[float, str]:
        """Seconds from lights-out to `crossing`, and how it was measured."""
        start = self.counter_for(crossing.clock, anchors)
        if start is None:
            logger.warning(
                f"No anchor for clock {crossing.clock!r} at lights-out — timing lap 1 from "
                f"arrival time instead"
            )
            return crossing.arrival - self.local, TIMING_ARRIVAL
        return (crossing.counter_ms - start) / 1000.0, TIMING_FROM_GO
