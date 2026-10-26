import collections
import time
import os
import json
import logging
import random
import signal
import threading
import urllib.request
import urllib.error
import paho.mqtt.client as mqtt
from lap_clock import ClockAnchors, Crossing, interval_s
from race_manager import CROSSING_COUNTED, RaceManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
api_url = os.getenv('API_URL', 'http://api:8000')
# Seconds, fractional allowed (a small test circuit can lap in under 2s). Only the
# fallback now: the staged race's session setting (race.min_lap_time) wins when present.
min_lap_time_s = float(os.getenv('MINIMUM_LAP_TIME', '2'))
# lapdata owns the whole start-light sequence: the 5 lights come on at
# START_LIGHT_INTERVAL spacing, then after a random hold all lights go out (race
# goes). The lit-count is published in race_state.start_lights so every client
# (browser, future hardware light bar) renders identical, in-sync lights — no
# client runs its own countdown clock.
# Last-resort lap target, used only when neither the race_control message nor the
# /races/pending/ payload carries one — i.e. an API image older than the target_laps
# field. The session's own end_condition_info is the real source.
DEFAULT_TARGET_LAPS = 20
light_interval = float(os.getenv('START_LIGHT_INTERVAL', '1.0'))
lights_out_hold_min = float(os.getenv('LIGHTS_OUT_HOLD_MIN', '0.5'))
lights_out_hold_max = float(os.getenv('LIGHTS_OUT_HOLD_MAX', '3.0'))
# Gap between `arm` (ArmedForStart is published immediately, all 5 lights off) and the
# first light coming on. Exists so every client has a couple of seconds with the
# countdown already on screen before anything moves — long enough for a freshly
# loaded browser tab to finish decoding its start-light beep sounds, which otherwise
# plays late/silent/glitchy on light 1 (Greg, 2026-09-27). Does not change the
# light-to-light spacing (still START_LIGHT_INTERVAL).
start_lights_pre_delay = float(os.getenv('START_LIGHTS_PRE_DELAY', '2.0'))

# Maps each Layer 1 clock onto our own time.monotonic(). Fed by every car_timestamp and
# every layer1_clock heartbeat; read by the race manager for lap 1 and for laps spanning
# a clock change. See lapdata/lap_clock.py.
anchors = ClockAnchors()
race = RaceManager(anchors)
pending_race_cache: dict | None = None
_light_timers: list = []  # the start-light sequence timers (5 lights + lights-out)
_end_timer: threading.Timer | None = None
_yellow_timers: list = []  # yellow-flag countdown ticks + the grace-expiry power cut
# One generation per timer sequence, bumped whenever that sequence is cancelled.
# Timer.cancel() can't stop a callback that has already started, so every callback
# re-checks it still belongs to the current sequence. Otherwise: a Resume Now landing at
# the instant of yellow expiry is overwritten by that timer's pause(), cutting power on a
# running race; an End during the countdown is undone by lights-out; a re-arm is started
# early by the previous arm's lights-out.
_start_generation = 0
_end_generation = 0
_yellow_generation = 0
# Every mutation of `race` holds this — MQTT messages on paho's thread and lapdata's own
# timers on theirs — so a timer's check-then-act can't interleave with a message.
_race_lock = threading.RLock()
# Last race state we POSTed to the API, so we fire /start and /finish exactly once
# per transition. lapdata (the race authority) owns these DB side-effects server-side
# so persistence is browser-independent — no client needs to be open.
_last_posted_state: str | None = None

# Capabilities of whichever Layer 1 is currently running, from its retained
# layer1_status message (empty until one arrives — treated the same as "no
# capabilities" so a browser never sees a capability that hasn't actually been
# confirmed). lapdata doesn't act on this itself; it's folded into race_state purely so
# React can grey out settings that need a capability the running Layer 1 lacks, and the
# Admin form can lock the yellow-flag power percentages without duplicating this
# subscription. See CLAUDE.md "Layer 1 capability advertising".
_layer1_capabilities: list = []

# Hardware-level: the last crossing seen per lane, for phantom-trigger filtering. None
# means "no crossing to compare against", which is where every lane starts and what
# lights-out resets them to — so the first crossing of a race is never filtered.
prev_crossing: list = [None] * 6

# car_timestamp is QoS 1 (#78), so a crossing can arrive twice: the broker resends one we
# hadn't acked when our session resumes. Keyed on the crossing itself, (clock,
# counter_ms) per car — the same key driver_laps uses — and compared for equality only,
# so no clock is ever parsed. A redelivery only ever repeats something recent, so a short
# window per car is enough.
DEDUP_WINDOW = 64
_recent_crossings: list = [collections.deque(maxlen=DEDUP_WINDOW) for _ in range(6)]
# For gap detection: the last car_timestamp `seq` seen per source, and the last `car_seq`
# per (source, car). `source` is one Layer 1 process, so a restarted Layer 1 is a new key
# rather than a sequence that went down. `seq` numbers every crossing a process publishes,
# whatever the car, so a loss shows on that process's very next crossing — the one that
# works for GPIO, which runs a process per lane sensor that a car moves between as it
# changes lane. `car_seq` is optional, from a Layer 1 that sees every car (BLE), and is
# what names the car, once it next crosses.
_last_seq: dict = {}
_last_car_seq: dict = {}
_seq_missing_warned = False

# Whether the last API call actually reached it. This is not a React-only "graceful
# degradation" concern: lapdata itself depends on the API for the pending-race queue and
# persists race lifecycle through it (publish_race_state()'s /start and /finish POSTs),
# so a genuinely unreachable API means the whole system's source of truth is down, not
# just a display losing a nicety. Published in every race_state (see publish_race_state)
# so every screen can show it — unmissably, per the "TV sized UI" rule, not a quiet log
# line nobody's watching mid-meet. Starts True (optimistic) so a display doesn't flash a
# false alarm before the first fetch has even happened.
_api_reachable = True
# Set when the startup load found the API down, so _api_recovery_loop tries again. Without
# it a lapdata that starts before the API sits empty until an operator happens to prepare.
_startup_load_pending = False


def _set_api_reachable(reachable: bool):
    """Update the reachability flag and, on any change, publish immediately rather than
    waiting for the next race event to carry it — a display should find out the app is
    dead (or has recovered) as soon as lapdata itself does."""
    global _api_reachable
    if reachable == _api_reachable:
        return
    _api_reachable = reachable
    try:
        publish_race_state()
    except Exception as e:
        logger.error(f"Failed to publish api_reachable change: {e}")


def fetch_pending_race() -> dict | None:
    """Read the next queued race (head of the session's pre-populated queue) from the
    API. Returns parsed JSON, or None when there is none (a plain 404 between sessions
    or before one is started — normal, and still means the API is reachable) or when the
    API itself could not be reached (abnormal — see _api_reachable above). Read-only —
    never creates a race."""
    try:
        url = f"{api_url}/races/pending/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            _set_api_reachable(True)
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _set_api_reachable(True)  # reachable; there's just nothing queued right now
        else:
            _set_api_reachable(False)
            logger.error(f"API returned {e.code} when fetching pending race: {e}")
    except Exception as e:
        _set_api_reachable(False)
        logger.error(f"API unreachable when fetching pending race: {e}")
    return None


def _parse_crossing(data: dict, arrival: float) -> Crossing | None:
    """Validate a car_timestamp payload into a Crossing, or None to drop it.

    There is deliberately no fallback to the old wall-clock `timestamp` format (see
    docs/lap-timing-plan.md decision 4: the contract changes in one step). A Layer 1
    image older than this one would otherwise publish laps that look plausible and are
    timed on a different basis, which is far worse at a meet than counting nothing and
    saying loudly why. The deploy step exists to make sure there is no stale image.
    """
    clock = data.get('clock')
    counter_ms = data.get('counter_ms')
    if not isinstance(clock, str) or not clock:
        logger.error(f"Dropping car_timestamp with no usable 'clock' ({clock!r}) — a Layer 1 "
                     f"image is older than lapdata. No laps will be counted until it is updated.")
        return None
    # bool is an int subclass, and True would sail through as counter_ms 1.
    if isinstance(counter_ms, bool) or not isinstance(counter_ms, int) or counter_ms < 0:
        logger.error(f"Dropping car_timestamp with bad 'counter_ms' ({counter_ms!r}) — a Layer 1 "
                     f"image is older than lapdata. No laps will be counted until it is updated.")
        return None
    return Crossing(clock=clock, counter_ms=counter_ms, arrival=arrival)


def _to_unix(local: float) -> float:
    """A lapdata time.monotonic() value as unix seconds. Display and logging only —
    nothing that times a lap goes through here."""
    return time.time() - time.monotonic() + local


def _is_seq(value) -> bool:
    # bool is an int subclass, as for counter_ms.
    return not isinstance(value, bool) and isinstance(value, int) and value >= 1


def _lost_since(table: dict, key, seq: int, what: str) -> int:
    """Record `seq` as the latest for `key`, returning how many numbers were skipped. The
    first seen for a key is only a baseline: a Layer 1 already running when we started
    has numbered crossings this process was never sent."""
    previous = table.get(key)
    if previous is not None and seq <= previous:
        # Not a redelivery (the crossing key would have caught that), and a restarted
        # Layer 1 has a new source — so something is publishing out of order.
        logger.warning(f"car_timestamp: {what} {seq} after {previous}")
        return 0
    table[key] = seq
    return seq - previous - 1 if previous is not None else 0


def _check_sequence(lane: int, source, seq, car_seq):
    """Log, loudly, a car_timestamp that never reached us. A jump in Layer 1's numbering
    means crossings were lost on the way. They can't be recovered — a driver is a lap
    short and their next lap reads as a multiple — but a missing lap found after the
    meet with no explanation is the worst kind of fault. Can't see a car crossing twice
    while BLE was disconnected: the powerbase keeps only the latest stamp, so Layer 1
    never knew either."""
    global _seq_missing_warned
    if not isinstance(source, str) or not source or not _is_seq(seq):
        if not _seq_missing_warned:
            _seq_missing_warned = True
            logger.warning(f"car_timestamp without a usable source/seq ({source!r}, {seq!r}) — a "
                           f"Layer 1 image is older than lapdata. Laps still count, but a lost "
                           f"crossing can't be detected until it is updated.")
        return
    per_car = _is_seq(car_seq)
    lost = _lost_since(_last_seq, source, seq, f"seq from {source}")
    if lost:
        car = ("a later LOST CROSSING line names the car once it crosses again" if per_car
               else "this Layer 1 can't say which car")
        logger.error(f"LOST CROSSING: {lost} car_timestamp(s) from {source} never arrived "
                     f"(seq {seq - lost - 1} then {seq}) — {car}. If they were racing, a driver "
                     f"is a lap short and their next lap time covers more than one lap.")
    if per_car:
        lost = _lost_since(_last_car_seq, (source, lane), car_seq, f"car {lane} car_seq from {source}")
        if lost:
            logger.error(f"LOST CROSSING: car {lane} — {lost} car_timestamp(s) from {source} "
                         f"never arrived (car_seq {car_seq - lost - 1} then {car_seq}). If they "
                         f"were racing, that driver is {lost} lap(s) short and their next lap "
                         f"time covers more than one lap.")


def handle_car_timestamp(data: dict, arrival: float):
    """Process a raw hardware crossing. Filters phantoms, publishes lap, updates race state."""
    lane = data['car']
    idx = lane - 1

    crossing = _parse_crossing(data, arrival)
    if crossing is None:
        return

    key = (crossing.clock, crossing.counter_ms)
    if key in _recent_crossings[idx]:
        logger.info(f"car_timestamp: car={lane} counter={crossing.counter_ms}ms clock={crossing.clock} "
                    f"already handled (redelivery) — ignored")
        return
    _recent_crossings[idx].append(key)
    _check_sequence(lane, data.get('source'), data.get('seq'), data.get('car_seq'))

    # Every crossing doubles as a clock sample, on top of the layer1_clock heartbeat.
    anchors.observe(crossing.clock, crossing.counter_ms, arrival)

    # Phantom filter, on Layer 1's counter rather than arrival times: a delayed
    # notification must not be able to push two genuine crossings under MINIMUM_LAP_TIME
    # and silently drop a real lap.
    previous = prev_crossing[idx]
    elapsed = None
    if previous is not None:
        elapsed, _ = interval_s(previous, crossing, anchors)
        if elapsed <= (race.min_lap_time if race.min_lap_time is not None else min_lap_time_s):
            return  # phantom trigger — too soon after last crossing

    prev_crossing[idx] = crossing

    crossing_local = anchors.to_local(crossing.clock, crossing.counter_ms)
    crossing_unix = _to_unix(crossing_local if crossing_local is not None else arrival)

    # Publish the normalised lap event — the stable public interface for all consumers.
    # lapTime is null for a lane's first crossing since lights-out: there is genuinely
    # no interval to report, where the old code invented one from a seeded previous time.
    client.publish('lap', json.dumps({
        'type': 'lap',
        'car': lane,
        'time': crossing_unix,
        'lapTime': round(elapsed, 3) if elapsed is not None else None,
    }))
    logger.info(f"lap: lane={lane} counter={crossing.counter_ms}ms clock={crossing.clock}")

    outcome = race.on_lap(lane, crossing)
    if outcome:
        publish_race_state()

        # Emit a context-rich event for the DB writer for every crossing the race manager
        # acted on, saying what it made of it (#86): a counted lap, or a void crossing
        # (the discarded start-line part-lap, a crossing after a yellow-flag grace, a
        # timing baseline) recorded for traceability. Ignored crossings (idle, not racing,
        # finished) produce nothing. The DB writer persists it verbatim without
        # re-deriving any race logic.
        d = race.drivers.get(lane)
        if d:
            counted = outcome == CROSSING_COUNTED
            # QoS 1 (#77): the broker queues it for dbwriter's persistent session while
            # dbwriter is down, and paho holds it here while our own link is down.
            # Redelivery is safe: driver_laps is keyed on (driver_race_id, clock,
            # counter_ms), so a duplicate is dropped.
            client.publish('driver_lap', qos=1, payload=json.dumps({
                'race_id': race.race_id,
                'driver_id': d.driver_id,
                'lane': lane,
                'outcome': outcome,
                # The raw ordinal of this lap, before any lap penalty. Penalties are
                # persisted separately (race_penalties) and subtracted only when results
                # are built — laps_completed here would subtract them twice (#83). A void
                # crossing is not a lap, so it has no number and no time.
                'lap_number': len(d.lap_times) if counted else None,
                'lap_time': d.lap_times[-1] if counted else None,
                # Provenance: which clock the crossing was on and where on it it fell —
                # persisted in driver_laps for every crossing (#27), the only way to
                # re-check a disputed lap after the meet — and how the interval was derived
                # ('counter' is exact; 'from_go' and 'anchored' went through the clock
                # anchor), which isn't stored since it follows from consecutive rows.
                'clock': crossing.clock,
                'counter_ms': crossing.counter_ms,
                'timing': d.last_lap_timing if counted else None,
                # The crossing as unix time, the same value the `lap` message carries.
                # For people reading driver_laps; nothing times a lap with it.
                'crossed_at': crossing_unix,
            }))

        # After the driver_lap, so the void crossing a penalty names is recorded first.
        publish_pending_penalties()

        if race.state == 'Finished':
            logger.info("Race finished — waiting for next race_control start")


def handle_layer1_clock(data: dict, arrival: float):
    """A bare (clock, counter) reading from Layer 1, pairing its counter with our clock.

    This is what makes lap 1 accurate. Crossings alone would anchor the clock too, but
    only once a car has crossed — and lap 1 is timed from lights-out, before any of that.
    The BLE Layer 1 feeds this from the Throttle characteristic (plan A, confirmed by
    HW-12 on 2026-09-20: throttleTimestamp is a live reading of the Slot clock), at
    ~3.3 samples/s with a median lateness of 1ms, so the anchor is essentially exact by
    the time the lights go out. GPIO sends one a second off its own monotonic clock.
    """
    clock = data.get('clock')
    counter_ms = data.get('counter_ms')
    if not isinstance(clock, str) or not clock:
        return
    if isinstance(counter_ms, bool) or not isinstance(counter_ms, int) or counter_ms < 0:
        return
    anchors.observe(clock, counter_ms, arrival)


def _time_expiry(generation: int):
    """Return the timer callback that auto-ends a time-limited race at race_end_time.

    Ends a Yellow or Paused race too: a yellow flag doesn't stop the race clock (see
    CLAUDE.md), and this timer fires only once, so skipping those states would leave a
    timed race with no end at all."""
    def _cb():
        with _race_lock:
            if generation != _end_generation or race.state not in ('Running', 'Yellow', 'Paused'):
                return
            _cancel_yellow_timers()
            race.end()
            publish_race_state()
            logger.info(f"Race {race.race_id} ended by time expiry")
    return _cb


def _cancel_end_timer():
    """Cancel the time-expiry timer, disarming it even if its callback has started."""
    global _end_timer, _end_generation
    _end_generation += 1
    if _end_timer and _end_timer.is_alive():
        _end_timer.cancel()
    _end_timer = None


def _schedule_end_timer():
    """Start the time-expiry timer if this race has a race_end_time."""
    global _end_timer
    _cancel_end_timer()
    if race.race_end_time:
        delay = race.race_end_time - time.time()
        if delay > 0:
            _end_timer = threading.Timer(delay, _time_expiry(_end_generation))
            _end_timer.daemon = True
            _end_timer.start()
            logger.info(f"Race end timer set for {delay:.1f}s")


def _yellow_tick(generation: int, seconds_left: int):
    """Return a timer callback that ticks race_state.yellow_seconds_left down and
    publishes it. lapdata owns the countdown for the same reason it owns the start
    lights: every display — including a trackside phone whose clock is wrong — shows
    the number it is sent instead of running its own timer."""
    def _cb():
        with _race_lock:
            if generation != _yellow_generation or race.state != 'Yellow':
                return
            race.yellow_seconds_left = seconds_left
            publish_race_state()
    return _cb


def _yellow_expiry(generation: int):
    """Return the timer callback that ends the grace period by moving to Paused.
    Calls race.pause() directly rather than routing through a race_control message —
    BLE's handle_race_state() reacts to the resulting Paused race_state to send the
    session's configured post-grace power, since this transition is never announced any
    other way. Passing from_yellow_expiry=True is what makes on_lap() eligible to apply
    the lap penalty (a manual race.pause() elsewhere never sets it)."""
    def _cb():
        with _race_lock:
            if generation != _yellow_generation or race.state != 'Yellow':
                return
            race.pause(power_pct=race.yellow_post_grace_power_pct, from_yellow_expiry=True)
            publish_race_state()
            logger.info(f"Race {race.race_id} yellow grace expired — power cut")
    return _cb


def _cancel_yellow_timers():
    """Cancel the yellow countdown/expiry timers. Bumping the generation also disarms
    a callback that has already started and is waiting on _race_lock."""
    global _yellow_timers, _yellow_generation
    _yellow_generation += 1
    for t in _yellow_timers:
        if t.is_alive():
            t.cancel()
    _yellow_timers = []


def _schedule_yellow_sequence():
    """After race.yellow(): tick yellow_seconds_left down once a second, then cut power
    when yellow_grace_seconds is up. Call _cancel_yellow_timers() before race.yellow()."""
    global _yellow_timers
    generation = _yellow_generation
    grace = race.yellow_grace_seconds
    # Countdown shows k from (grace - k)s in, so a fractional grace still reaches 1
    # exactly one second before the cut.
    timers = [
        threading.Timer(max(0.0, grace - k), _yellow_tick(generation, k))
        for k in range(race.yellow_seconds_left - 1, 0, -1)
    ]
    timers.append(threading.Timer(max(0.0, grace), _yellow_expiry(generation)))
    for t in timers:
        t.daemon = True
        t.start()
    _yellow_timers = timers


def _lights_out(generation: int):
    """Return the timer callback that fires lights out, transitioning the race to Running."""
    def _cb():
        global pending_race_cache, prev_crossing
        # "Go" is this instant, not the instant we get the lock. Every lap 1 in the race
        # is timed from this value, so waiting on _race_lock behind a crossing must not
        # land in it. If the generation check below then fails, it is simply discarded.
        go = time.monotonic()
        with _race_lock:
            if generation != _start_generation or race.state != 'ArmedForStart':
                return
            race.start(go)
            prev_crossing = [None] * 6
            _schedule_end_timer()
            publish_race_state()
        # Outside the lock: an HTTP call (5s timeout) must not hold up the crossings
        # arriving in the first seconds after lights out.
        pending_race_cache = fetch_pending_race()
    return _cb


def _cancel_start_timers():
    """Cancel any pending start-light/lights-out timers, disarming them even if a
    callback has already started."""
    global _light_timers, _start_generation
    _start_generation += 1
    for t in _light_timers:
        if t.is_alive():
            t.cancel()
    _light_timers = []


def _set_start_lights(generation: int, n: int):
    """Return a timer callback that lights the Nth start light and publishes state."""
    def _cb():
        with _race_lock:
            if generation != _start_generation or race.state != 'ArmedForStart':
                return
            race.start_lights = n
            publish_race_state()
    return _cb


def _schedule_start_sequence():
    """Light the 5 start lights at fixed intervals, then lights out → Running.

    lapdata owns the whole sequence and publishes start_lights in race_state, so
    every client renders the same lights at the same moment (no per-client clock).
    race.arm() (called just before this) already published ArmedForStart with all 5
    lights off, so START_LIGHTS_PRE_DELAY is pure dead air before light 1 — every
    client is already showing the countdown, just not moving yet.
    """
    global _light_timers
    _cancel_start_timers()
    generation = _start_generation
    timers = [
        threading.Timer(start_lights_pre_delay + light_interval * (i - 1), _set_start_lights(generation, i))
        for i in range(1, 6)
    ]
    hold = random.uniform(lights_out_hold_min, lights_out_hold_max)
    lights_out_at = start_lights_pre_delay + light_interval * 4 + hold
    timers.append(threading.Timer(lights_out_at, _lights_out(generation)))
    for t in timers:
        t.daemon = True
        t.start()
    _light_timers = timers
    logger.info(
        f"Race {race.race_id} armed — first light at t+{start_lights_pre_delay:.1f}s, "
        f"5 lights at {light_interval:.1f}s spacing, "
        f"lights out at t+{lights_out_at:.1f}s"
    )


def _load_pending(pending: dict, target_laps: int | None = None):
    """Load a /races/pending/ payload into the race manager (state becomes NotStarted).

    The payload carries the session's own lap target, so that is the default. An explicit
    target_laps (from a race_control arm/start message) still wins, since that is a
    deliberate instruction from a client. DEFAULT_TARGET_LAPS is only reached against an
    API image old enough not to send one.

    ⚠️ This used to be a hardcoded 20 at every call site, because /races/pending/ carried
    no lap target: a session set to 5 laps staged and displayed as 20, and only became 5
    when RaceControl armed it with a value it had looked up itself.
    """
    if target_laps is None:
        target_laps = pending.get('target_laps')
    if target_laps is None:
        target_laps = DEFAULT_TARGET_LAPS
    race.load_lineup(
        pending['race_id'], pending.get('race_number'), target_laps,
        pending['lane_assignments'], pending.get('count_first_crossing', False),
        session_type=pending.get('session_type', 'Points'),
        race_duration_seconds=pending.get('race_duration_seconds'),
        session_drivers=pending.get('session_drivers', []),
        yellow_grace_seconds=pending.get('yellow_grace_seconds', 5),
        yellow_grace_power_pct=pending.get('yellow_grace_power_pct', 100),
        yellow_post_grace_power_pct=pending.get('yellow_post_grace_power_pct', 0),
        yellow_lap_penalty_laps=pending.get('yellow_lap_penalty_laps', 0),
        min_lap_time=pending.get('min_lap_time'),
    )


def handle_race_control(data: dict, arrival: float):
    """Process a race_control command from any client (browser, button box, etc.).

    `arrival` is when the message landed, on time.monotonic() and stamped before the
    race lock. The immediate 'start' command (no start-light countdown) uses it as
    lights-out, for the same reason _lights_out() takes its own: lap 1 is timed from it.
    """
    global pending_race_cache, prev_crossing
    command = data.get('command')
    logger.info(f"race_control: {command}")

    if command == 'arm':
        race_id = data.get('race_id')
        target_laps = data.get('target_laps')

        _cancel_start_timers()
        _cancel_yellow_timers()
        _cancel_end_timer()

        # Re-read rather than trust the cache: NextRace edits the queued lineup through
        # the API after it was staged (add a driver, toggle a lane), and a cached lineup
        # would silently leave those drivers' laps uncounted. The race is still
        # NotStarted, so the queue head is this race. The cache is only the fallback
        # for an API that is unreachable at the moment of arming.
        #
        # ⚠️ "Unreachable" means `fresh` itself is falsy — not merely that its race_id
        # disagrees with the caller's. A stale `race_id` in the request (an operator's
        # browser tab that hasn't refreshed since the queue changed underneath it — e.g.
        # a database reseed, or another client's regenerate-races) must still arm
        # whatever the live API says is actually pending, not a same-numbered leftover
        # in `pending_race_cache` from a previous, unrelated race. Once bit us for real:
        # after a full DB reseed mid-session, lapdata (never restarted, so still holding
        # a pre-reseed cache) armed and ran an entire race on stale cached data — wrong
        # driver names throughout, and its start/finish POSTs landed on whatever race the
        # reused id now pointed to post-reseed.
        fresh = fetch_pending_race()
        if fresh:
            if race_id is not None and fresh.get('race_id') != race_id:
                logger.warning(
                    f"arm requested race {race_id} but the live queue head is "
                    f"{fresh.get('race_id')} — arming the live one"
                )
            pending = fresh
        elif pending_race_cache and pending_race_cache.get('race_id') == race_id:
            pending = pending_race_cache
        else:
            pending = None

        if not pending:
            logger.error("Cannot arm: failed to load pending race from API")
            return

        pending_race_cache = pending
        _load_pending(pending, target_laps)
        race.arm()
        publish_race_state()

        _schedule_start_sequence()

    elif command == 'start':
        race_id = data.get('race_id')
        target_laps = data.get('target_laps')

        _cancel_end_timer()

        # Use the pre-cached lineup when the race_id matches — avoids the timing
        # issue where POST /races/N/start has already run by the time we fetch,
        # causing fetch_pending_race() to return Race N+1 instead of Race N.
        if pending_race_cache and pending_race_cache.get('race_id') == race_id:
            pending = pending_race_cache
        else:
            pending = fetch_pending_race()

        if not pending:
            logger.error("Cannot start: failed to load pending race from API")
            return

        _load_pending(pending, target_laps)
        race.start(arrival)
        # Forget the previous race's crossings so no phantom laps bleed across race start
        prev_crossing = [None] * 6
        _schedule_end_timer()
        publish_race_state()

        # Cache the next queued race (the new head, now this one is Running). The
        # whole session is pre-populated, so this only reads — it never creates.
        pending_race_cache = fetch_pending_race()

    elif command == 'prepare':
        # "Next Race" on the race-control page. Read the head of the session's race
        # queue (already pre-populated — no generation here), load it into the race
        # manager, and publish a NotStarted race_state so every display (currentrace,
        # nextrace) stages the new lineup — the same shape lapdata broadcasts at
        # startup, so this is not a new state.
        race_id = data.get('race_id')
        # Never over a race that is still under way: the queue head is the *next* race, and
        # loading it would throw away this one's laps and its /finish. A client can send
        # prepare from a stale view (RaceControl after ending a stuck race, or regenerating
        # while Paused); End first is the only way to move on.
        if race.state in ('ArmedForStart', 'Running', 'Yellow', 'Paused'):
            logger.warning(f"prepare ignored: race {race.race_id} is {race.state} (end it first)")
            return
        fresh = fetch_pending_race()
        if fresh:
            pending_race_cache = fresh
            _load_pending(fresh)
            publish_race_state()
            logger.info(f"Staged race {fresh.get('race_id')} on prepare (requested {race_id})")
        else:
            # No queued race (e.g. session just ended / not started yet). Nothing to
            # stage — the operator starts the next session before the next race exists.
            logger.info("prepare: no queued race to stage (start a session first)")

    elif command == 'status':
        # No longer needed to get the state — race_state is retained and heartbeated
        # (#76), and the heartbeat re-probes a down API — but still answered, so an older
        # client that asks isn't left waiting.
        publish_race_state()

    elif command == 'reload_lineup':
        # NextRace edited the queued lineup through the API (added/removed a driver,
        # toggled a lane, swapped a car). Re-stage it so race_state — and every display
        # built from it — matches. Only while the staged race hasn't started: once it
        # is armed the lineup is fixed, and mid-race the queue head is the *next* race,
        # which must not replace the one running.
        if race.state != 'NotStarted':
            logger.info(f"reload_lineup ignored: race {race.race_id} is {race.state}")
            return
        fresh = fetch_pending_race()
        if not fresh:
            return
        if race.race_id is not None and fresh.get('race_id') != race.race_id:
            logger.info(f"reload_lineup ignored: queue head is race {fresh.get('race_id')}, "
                        f"staged race is {race.race_id} (use prepare to advance)")
            return
        pending_race_cache = fresh
        _load_pending(fresh)
        publish_race_state()

    elif command == 'yellow':
        # Grace period, then power cut: cars keep racing at full power for
        # yellow_grace_seconds while lapdata publishes a once-a-second countdown, then
        # the race moves to Paused (BLE reacts to that race_state transition by cutting
        # power). Operator can still cancel early with 'resume' ("Resume Now").
        _cancel_yellow_timers()
        race.yellow()
        publish_race_state()
        _schedule_yellow_sequence()

    elif command == 'pause':
        # Immediate, no-grace stop — distinct from 'yellow', which delays the cut. Also
        # what BLE sends, with a `reason`, when it has stopped the cars over a lost link.
        if _stop_race(data.get('reason') or 'pause requested'):
            publish_race_state()

    elif command == 'resume':
        _cancel_yellow_timers()
        race.resume()
        publish_race_state()

    elif command == 'end':
        _cancel_start_timers()
        _cancel_yellow_timers()
        _cancel_end_timer()
        race.end()
        publish_race_state()

    else:
        logger.warning(f"Unknown race_control command: {command}")


def _stop_race(reason: str) -> bool:
    """Stop the race. Caller holds _race_lock and publishes if this returns True.

    ⚠️ Any connection loss stops the race (Greg, 2026-10-25): a link that is down is a
    lap that can't be counted. BLE stops the cars; this makes the race say so, and an
    operator resumes it. Racing -> Paused (a manual-style pause, so never a yellow-flag
    penalty). During the start lights the start is aborted instead, since a Paused race
    has no lights-out to resume from. Anything else is left alone: pausing a staged or
    finished race would break it."""
    if race.state in RaceManager.COUNTING_STATES:
        _cancel_yellow_timers()
        race.pause()
    elif race.state == 'ArmedForStart':
        _cancel_start_timers()
        race.abort_start()
    else:
        return False
    logger.warning(f"Race {race.race_id} stopped: {reason}")
    return True


def on_disconnect(_client, _userdata, _flags, _reason_code, _properties):
    """We can't hear crossings, and nothing can hear us. Paused here, the race is
    republished by on_connect when the broker is back."""
    with _race_lock:
        _stop_race('lapdata lost the MQTT broker')


def _post_api(path: str, json_body: dict | None = None):
    """Fire-and-forget POST to the API in a daemon thread (never blocks MQTT)."""
    def _do():
        try:
            data = json.dumps(json_body).encode('utf-8') if json_body is not None else None
            headers = {'Content-Type': 'application/json'} if data is not None else {}
            req = urllib.request.Request(f"{api_url}{path}", data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
            _set_api_reachable(True)
        except Exception as e:
            logger.warning(f"API POST {path} failed: {e}")
            _set_api_reachable(False)
    threading.Thread(target=_do, daemon=True).start()


def publish_pending_penalties():
    """Publish each penalty race_manager applied since the last call as its own
    `driver_penalty` event (#88), currently only a yellow-flag lap penalty. dbwriter
    writes it to race_penalties, the one penalty record; the leaderboard will announce it
    (#89). Its own topic, not a crossing outcome: a void crossing may cost 0 or more laps,
    and a future penalty (a jump start, an operator's) may have no crossing at all.

    QoS 1 (#94), like driver_lap: the broker queues it for dbwriter's persistent session.
    Redelivery is safe because each record carries the penalty_id race_manager minted
    when it applied the penalty, and race_penalties is unique on it."""
    for record in race.pending_penalty_records:
        client.publish('driver_penalty', qos=1,
                       payload=json.dumps({'race_id': race.race_id, **record}))
        logger.info(f"driver_penalty: race={race.race_id} {record}")
    race.pending_penalty_records = []


def publish_race_state():
    global _last_posted_state
    state_dict = race.to_dict()
    # Not race-manager business (race_manager.py is pure/DB-free), so it's folded in
    # here rather than in RaceManager.to_dict() — see _api_reachable above.
    state_dict['api_reachable'] = _api_reachable
    state_dict['capabilities'] = _layer1_capabilities
    # Retained, so a subscriber that (re)connects gets the current state at once (#76).
    client.publish('race_state', json.dumps(state_dict), retain=True)

    # Persist race-lifecycle transitions via the API (race Running/Finished, session
    # InProgress, and the automatic session-end). Starting the next race/session stays
    # a manual /racecontrol action, so we only POST start/finish — never advance.
    state = race.state
    if state != _last_posted_state:
        if state == 'Running':
            _post_api(f"/races/{race.race_id}/start", {"started_at": race.race_start_time})
        elif state == 'Finished':
            _post_api(f"/races/{race.race_id}/finish")
        _last_posted_state = state


def handle_layer1_status(data: dict):
    """Store the capabilities of whichever Layer 1 is currently running (a retained
    message, so this fires immediately on every connect/reconnect). Never branch on
    data.get('layer1') here or anywhere downstream — only on the capabilities list."""
    global _layer1_capabilities
    _layer1_capabilities = data.get('capabilities', [])
    # Layer 1's Last Will: it can't publish crossings. (A Layer 1 that doesn't say is
    # online.) A powerbase link drop is deliberately not this — the crossings made while
    # it was down arrive on reconnect and must count, so BLE asks for the pause itself
    # once they're in.
    if data.get('online') is False:
        with _race_lock:
            if _stop_race(f"Layer 1 ({data.get('layer1')}) went offline"):
                publish_race_state()


def on_message(_client, _userdata, msg):
    # Stamp arrival FIRST, before parsing and before _race_lock. Every second spent
    # waiting for the lock would otherwise be added to this sample's apparent lateness,
    # and the anchor is a running minimum of exactly that.
    arrival = time.monotonic()
    try:
        data = json.loads(msg.payload.decode('utf-8', 'ignore'))
        # Deliberately outside _race_lock: a clock sample touches no race state, and
        # these arrive several times a second. Blocking them behind a crossing or a
        # timer callback would make them late, which is the one thing that degrades
        # the anchor. ClockAnchors has its own lock.
        if msg.topic == 'layer1_clock':
            handle_layer1_clock(data, arrival)
            return
        if msg.topic == 'layer1_status':
            handle_layer1_status(data)
            return
        with _race_lock:
            if msg.topic == 'car_timestamp':
                handle_car_timestamp(data, arrival)
            elif msg.topic == 'race_control':
                handle_race_control(data, arrival)
    except Exception as e:
        logger.error(f"Error handling {msg.topic}: {e}", exc_info=True)


def on_connect(_client, _userdata, _flags, _reason_code, _properties):
    # QoS 1 (#78): with our persistent session (see the client below) the broker queues
    # crossings while we're away and resends any we hadn't acked. The rest stay QoS 0, so
    # the broker queues none of them for us: a stale race_control replayed on reconnect
    # could stage or start a race, and a stale clock sample is only late.
    _client.subscribe('car_timestamp', qos=1)
    _client.subscribe('layer1_clock')
    _client.subscribe('layer1_status')
    _client.subscribe('race_control')
    logger.info("Connected to MQTT broker")

    # on_connect fires on every broker *re*connect too, not just startup. Reloading the
    # pending race then would replace a running race with the next one in the queue, so
    # once a race is loaded just republish it — the broker may hold our Last Will
    # (`Offline`) as the retained race_state, which must be replaced straight away.
    with _race_lock:
        if race.race_id:
            publish_race_state()
            return
    load_on_startup()


def fetch_running_recovery() -> dict | None:
    """The DB's record of a race still marked Running — lineup, start time, counted laps —
    or None if there isn't one, it can't be built, or the API can't be reached (only the
    last leaves _api_reachable False)."""
    try:
        with urllib.request.urlopen(f"{api_url}/races/running/recovery/", timeout=5) as resp:
            _set_api_reachable(True)
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # The API answered either way. A 500 here (say, a Running race whose session row
        # is broken) must not read as "API down": that would retry forever, show
        # Connection lost on every screen and never stage the queue head. Fall through to
        # the normal startup instead; RaceControl still offers to end the stuck race.
        _set_api_reachable(True)
        if e.code != 404:  # 404: nothing is Running
            logger.error(f"API returned {e.code} when fetching running-race recovery: {e}")
    except Exception as e:
        _set_api_reachable(False)
        logger.error(f"API unreachable when fetching running-race recovery: {e}")
    return None


def recover_running_race(recovery: dict) -> bool:
    """Rebuild a race the DB still calls Running but this process knows nothing about —
    lapdata restarted mid-race. Holds _race_lock. The race comes back Paused (see
    RaceManager.restore); if it had already run out of time or been won it comes back
    Finished and publish_race_state() POSTs the finish, which also runs the API's
    session auto-end — the step that never happened when this was a manual restart.
    Returns False, loading nothing, if the payload has no lineup to rebuild."""
    global pending_race_cache, _last_posted_state
    setup = recovery.get('setup')
    if not setup:
        logger.error(f"Race {recovery.get('race_id')} is Running in the DB but has no lineup — can't recover it")
        return False
    _load_pending(setup)
    race.restore(
        recovery.get('started_at'),
        {int(driver_id): times for driver_id, times in (recovery.get('laps') or {}).items()},
        time.time(),
        {int(driver_id): n for driver_id, n in (recovery.get('lap_penalties') or {}).items()},
        ({int(driver_id): n for driver_id, n in recovery['crossings'].items()}
         if recovery.get('crossings') is not None else None),
    )
    # The state we just rebuilt is what the API already holds (Running), or is a Finished
    # transition it must be told about. Either way, don't POST a bogus /start for it.
    _last_posted_state = 'Running' if race.state != 'Finished' else None
    if race.state != 'Finished':
        _schedule_end_timer()
    publish_race_state()
    pending_race_cache = None
    return True


def load_on_startup() -> bool:
    """Put something in the race manager at startup: a race the DB says is still Running
    (restarted mid-race) in preference to the queue head. Returns False if the API
    couldn't be reached, so the caller can try again."""
    global _startup_done
    try:
        return _load_on_startup()
    finally:
        _startup_done = True


def _load_on_startup() -> bool:
    global pending_race_cache, _startup_load_pending
    recovery = fetch_running_recovery()
    if recovery is None and not _api_reachable:
        _startup_load_pending = True
        logger.warning("API unreachable at startup — will retry until the race can be loaded")
        return False
    _startup_load_pending = False
    if recovery is not None:
        with _race_lock:
            if race.race_id:
                return True
            recovered = recover_running_race(recovery)
        if recovered:
            pending_race_cache = fetch_pending_race()
            return True
        # No lineup to rebuild: start up as if nothing were Running, so the queue head is
        # still staged. RaceControl offers to end the stuck race.

    pending = fetch_pending_race()
    if pending is None and not _api_reachable:
        # The API went away between the two reads — retry, same as if it had been down
        # for the first.
        _startup_load_pending = True
        logger.warning("API unreachable at startup — will retry until the race can be loaded")
        return False
    with _race_lock:
        if race.race_id:
            return True
        if pending:
            pending_race_cache = pending
            _load_pending(pending)
            publish_race_state()
        else:
            logger.warning("No pending race found on startup — waiting for race_control start")
    return True


# What the retained race_state says when lapdata is gone: its Last Will (an ungraceful
# disconnect), and what it publishes itself before a clean one. Consumers treat it as
# "nothing known" — BLE in particular keeps whatever power it last set. No race_id, so
# nothing reads it as a race that ended.
OFFLINE_STATE = json.dumps({'state': 'Offline', 'race_id': None, 'drivers': []})

# A fixed client id and clean_session=False make the broker keep our car_timestamp
# subscription, and queue crossings for it, across a disconnect or a restart (#78). paho
# acks each one when on_message returns, which catches everything, so a crossing is only
# resent if we died while handling it — and the dedup above drops it if it got that far.
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='lapdata', clean_session=False)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
# On a half-open link (a Pi power cut) the broker only fires this after 1.5x keepalive
# (7.5s, see connect below), so the heartbeat stopping is the faster signal; the will is
# the backstop.
client.will_set('race_state', OFFLINE_STATE, retain=True)

# Constructing the client is pure, connecting is not — so only the I/O sits behind the
# guard. That keeps this module importable by test_timestamps.py while the container
# (CMD ["python", "timestamps_to_lapdata.py"]) still runs as __main__ and connects.
API_RETRY_INTERVAL_S = 10

# race_state is republished this often whatever happens (#76): it heals a message a
# subscriber missed, and its absence is how a consumer tells that lapdata has gone.
# React's useLapdataAlive waits a few beats before calling lapdata offline.
HEARTBEAT_INTERVAL_S = 2
# Until the first startup load has been attempted, the race manager is empty only because
# nothing has been read yet. Beating that would make an empty NotStarted the retained
# state for a moment, mid-recovery.
_startup_done = False
_api_probe_running = threading.Lock()


def _probe_api():
    """One reachability check, never two at once: a down API takes 5s to time out,
    longer than a beat."""
    if not _api_probe_running.acquire(blocking=False):
        return
    try:
        fetch_pending_race()
    finally:
        _api_probe_running.release()


def _beat():
    if _startup_done:
        with _race_lock:
            publish_race_state()
    # This used to happen on a `status` request, which is what cleared a stale
    # "Connection lost" when a browser refreshed. A beat does it now, so the display
    # clears itself within a beat of the API coming back.
    if not _api_reachable and not _startup_load_pending:
        threading.Thread(target=_probe_api, daemon=True).start()


def _heartbeat_loop():
    while True:
        time.sleep(HEARTBEAT_INTERVAL_S)
        try:
            _beat()
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}", exc_info=True)


def _shutdown(_signum, _frame):
    """A clean disconnect doesn't fire the Last Will, so say Offline ourselves first."""
    logger.info("Shutting down: publishing Offline race_state")
    client.publish('race_state', OFFLINE_STATE, retain=True).wait_for_publish(timeout=2)
    client.disconnect()


def _api_recovery_loop():
    """Retry the startup load while the API was down when lapdata started, so nothing was
    loaded — a recovered Running race especially must not wait for someone to notice.
    Clearing api_reachable once the startup load is done is the heartbeat's job."""
    while True:
        time.sleep(API_RETRY_INTERVAL_S)
        if _startup_load_pending:
            load_on_startup()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _shutdown)
    threading.Thread(target=_api_recovery_loop, daemon=True).start()
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    # The broker fires our Last Will 1.5x keepalive after we silently vanish (a dropped
    # network, a hung process). Displays and BLE notice sooner from the missing beats,
    # but this is what makes the retained state itself say Offline.
    client.connect(mqtt_hostname, keepalive=5)
    client.loop_forever()
