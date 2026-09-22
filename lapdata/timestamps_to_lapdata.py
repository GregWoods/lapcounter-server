import time
import os
import json
import logging
import random
import threading
import urllib.request
import urllib.error
import paho.mqtt.client as mqtt
from lap_clock import ClockAnchors, Crossing, interval_s
from race_manager import RaceManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
api_url = os.getenv('API_URL', 'http://api:8000')
# Seconds, fractional allowed (a small test circuit can lap in under 2s).
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

# Hardware-level: the last crossing seen per lane, for phantom-trigger filtering. None
# means "no crossing to compare against", which is where every lane starts and what
# lights-out resets them to — so the first crossing of a race is never filtered.
prev_crossing: list = [None] * 6


def fetch_pending_race() -> dict | None:
    """Read the next queued race (head of the session's pre-populated queue) from the
    API. Returns parsed JSON, or None when there is none (404 between sessions / before
    one is started) or on failure. Read-only — never creates a race."""
    try:
        url = f"{api_url}/races/pending/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        logger.error(f"API unavailable when fetching pending race: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch pending race: {e}")
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


def handle_car_timestamp(data: dict, arrival: float):
    """Process a raw hardware crossing. Filters phantoms, publishes lap, updates race state."""
    lane = data['car']
    idx = lane - 1

    crossing = _parse_crossing(data, arrival)
    if crossing is None:
        return

    # Every crossing doubles as a clock sample, on top of the layer1_clock heartbeat.
    anchors.observe(crossing.clock, crossing.counter_ms, arrival)

    # Phantom filter, on Layer 1's counter rather than arrival times: a delayed
    # notification must not be able to push two genuine crossings under MINIMUM_LAP_TIME
    # and silently drop a real lap.
    previous = prev_crossing[idx]
    elapsed = None
    if previous is not None:
        elapsed, _ = interval_s(previous, crossing, anchors)
        if elapsed <= min_lap_time_s:
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

    # Capture lap count before processing so we can tell a real counted lap from a
    # discarded start-line crossing (both make on_lap return True).
    driver_before = race.drivers.get(lane)
    prev_laps = driver_before.laps_completed if driver_before else 0

    if race.on_lap(lane, crossing):
        publish_race_state()

        # Emit a context-rich event for the DB writer ONLY when a real lap was
        # counted. This is the authoritative lap (race manager already ignores
        # idle/non-running crossings and the discarded start crossing), so the DB
        # writer persists it verbatim without re-deriving any race logic.
        d = race.drivers.get(lane)
        if d and d.laps_completed > prev_laps:
            client.publish('driver_lap', json.dumps({
                'race_id': race.race_id,
                'driver_id': d.driver_id,
                'lane': lane,
                'lap_number': d.laps_completed,
                'lap_time': d.lap_times[-1],
                # Provenance: which clock timed this lap, where on it the crossing fell,
                # and how the interval was derived ('counter' is exact; 'from_go' and
                # 'anchored' went through the clock anchor). The DB writer ignores these
                # unless they are persisted later — they are the only way to re-check a
                # disputed lap after the meet.
                'clock': crossing.clock,
                'counter_ms': crossing.counter_ms,
                'timing': d.last_lap_timing,
            }))

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
    BLE's handle_race_state() reacts to the resulting Paused race_state to send
    POWER_ON_TIMER_HALT, since this transition is never announced any other way."""
    def _cb():
        with _race_lock:
            if generation != _yellow_generation or race.state != 'Yellow':
                return
            race.pause()
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
    """
    global _light_timers
    _cancel_start_timers()
    generation = _start_generation
    timers = [
        threading.Timer(light_interval * i, _set_start_lights(generation, i)) for i in range(1, 6)
    ]
    hold = random.uniform(lights_out_hold_min, lights_out_hold_max)
    lights_out_at = light_interval * 5 + hold
    timers.append(threading.Timer(lights_out_at, _lights_out(generation)))
    for t in timers:
        t.daemon = True
        t.start()
    _light_timers = timers
    logger.info(
        f"Race {race.race_id} armed — 5 lights at {light_interval:.1f}s spacing, "
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
        # A client (e.g. the race-control page) asking for the current state,
        # since race_state is not retained on the broker.
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
        # Immediate, no-grace stop — distinct from 'yellow', which delays the cut.
        _cancel_yellow_timers()
        race.pause()
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


def _post_api(path: str, json_body: dict | None = None):
    """Fire-and-forget POST to the API in a daemon thread (never blocks MQTT)."""
    def _do():
        try:
            data = json.dumps(json_body).encode('utf-8') if json_body is not None else None
            headers = {'Content-Type': 'application/json'} if data is not None else {}
            req = urllib.request.Request(f"{api_url}{path}", data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            logger.warning(f"API POST {path} failed: {e}")
    threading.Thread(target=_do, daemon=True).start()


def publish_race_state():
    global _last_posted_state
    client.publish('race_state', json.dumps(race.to_dict()))

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
        with _race_lock:
            if msg.topic == 'car_timestamp':
                handle_car_timestamp(data, arrival)
            elif msg.topic == 'race_control':
                handle_race_control(data, arrival)
    except Exception as e:
        logger.error(f"Error handling {msg.topic}: {e}", exc_info=True)


def on_connect(_client, _userdata, _flags, _reason_code, _properties):
    _client.subscribe('car_timestamp')
    _client.subscribe('layer1_clock')
    _client.subscribe('race_control')
    logger.info("Connected to MQTT broker")

    # on_connect fires on every broker *re*connect too, not just startup. Reloading the
    # pending race then would replace a running race with the next one in the queue, so
    # once a race is loaded just republish it — race_state isn't retained on the broker.
    global pending_race_cache
    with _race_lock:
        if race.race_id:
            publish_race_state()
            return

    # Load pending race on startup so race state is available immediately
    pending = fetch_pending_race()
    with _race_lock:
        if pending:
            pending_race_cache = pending
            _load_pending(pending)
            publish_race_state()
        else:
            logger.warning("No pending race found on startup — waiting for race_control start")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

# Constructing the client is pure, connecting is not — so only the I/O sits behind the
# guard. That keeps this module importable by test_timestamps.py while the container
# (CMD ["python", "timestamps_to_lapdata.py"]) still runs as __main__ and connects.
if __name__ == '__main__':
    client.connect(mqtt_hostname)
    client.loop_forever()
