import time
import os
import json
import logging
import random
import threading
import urllib.request
import urllib.error
import paho.mqtt.client as mqtt
from race_manager import RaceManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
api_url = os.getenv('API_URL', 'http://api:8000')
min_lap_time_ns = int(os.getenv('MINIMUM_LAP_TIME', '2')) * 1_000_000_000
# How far a Layer 1's crossing timestamp may sit from our own clock before we stop
# trusting it. Generous: every Layer 1 runs on this same machine, so a legitimate
# stamp is milliseconds old, but a container that has just started while the Pi's
# clock is being set by hand deserves some slack before we start shouting.
HW_TIMESTAMP_TOLERANCE_NS = 30 * 1_000_000_000
# lapdata owns the whole start-light sequence: the 5 lights come on at
# START_LIGHT_INTERVAL spacing, then after a random hold all lights go out (race
# goes). The lit-count is published in race_state.start_lights so every client
# (browser, future hardware light bar) renders identical, in-sync lights — no
# client runs its own countdown clock.
light_interval = float(os.getenv('START_LIGHT_INTERVAL', '1.0'))
lights_out_hold_min = float(os.getenv('LIGHTS_OUT_HOLD_MIN', '0.5'))
lights_out_hold_max = float(os.getenv('LIGHTS_OUT_HOLD_MAX', '3.0'))

race = RaceManager()
pending_race_cache: dict | None = None
_light_timers: list = []  # the start-light sequence timers (5 lights + lights-out)
_end_timer: threading.Timer | None = None
# Last race state we POSTed to the API, so we fire /start and /finish exactly once
# per transition. lapdata (the race authority) owns these DB side-effects server-side
# so persistence is browser-independent — no client needs to be open.
_last_posted_state: str | None = None

# Hardware-level: last crossing time per lane (nanoseconds) for phantom-trigger filtering
prev_crossing_ns = [time.time_ns() - min_lap_time_ns - 1 for _ in range(6)]


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


def _crossing_ns(data: dict) -> int:
    """When the crossing actually happened, per Layer 1 — not when we got told.

    Every Layer 1 already stamps `timestamp` at detection: GPIO in its interrupt
    callback, BLE from the powerbase's own millisecond sensor clock. Re-stamping on
    arrival here would throw that away and fold MQTT/queueing latency into lap times.
    That was tolerable for GPIO (interrupt-driven, so arrival ≈ crossing) but not for
    BLE, whose Slot characteristic is round-robin across 6 cars and can report a
    crossing up to a full cycle late.

    Falls back to arrival time if the stamp is missing or implausible — a Layer 1 with
    a broken clock must not be able to poison race timing, and on the Pi (no RTC, clock
    set by hand before a meet) that is a real possibility. Same machine, same clock, so
    a sane stamp is always within a second or two of now.
    """
    now_ns = time.time_ns()
    stamp = data.get('timestamp')
    if stamp is None:
        return now_ns
    try:
        stamp = int(stamp)
    except (TypeError, ValueError):
        logger.warning(f"Ignoring non-numeric car_timestamp {stamp!r}")
        return now_ns
    if abs(now_ns - stamp) > HW_TIMESTAMP_TOLERANCE_NS:
        logger.warning(
            f"Ignoring implausible car_timestamp: {(now_ns - stamp) / 1e9:+.1f}s from now. "
            f"Layer 1 clock out of step? Falling back to arrival time."
        )
        return now_ns
    return stamp


def handle_car_timestamp(data: dict):
    """Process a raw hardware crossing. Filters phantoms, publishes lap, updates race state."""
    lane = data['car']
    idx = lane - 1

    now_ns = _crossing_ns(data)
    elapsed_ns = now_ns - prev_crossing_ns[idx]
    if elapsed_ns <= min_lap_time_ns:
        return  # phantom trigger — too soon after last crossing

    prev_crossing_ns[idx] = now_ns
    crossing_time = now_ns / 1e9  # seconds, used by race manager for lap timing

    # Publish the normalised lap event — the stable public interface for all consumers
    client.publish('lap', json.dumps({
        'type': 'lap',
        'car': lane,
        'time': crossing_time,
        'lapTime': elapsed_ns / 1e9,
    }))
    logger.info(f"lap: lane={lane} t={crossing_time:.3f}")

    # Capture lap count before processing so we can tell a real counted lap from a
    # discarded start-line crossing (both make on_lap return True).
    driver_before = race.drivers.get(lane)
    prev_laps = driver_before.laps_completed if driver_before else 0

    if race.on_lap(lane, crossing_time):
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
            }))

        if race.state == 'Finished':
            logger.info("Race finished — waiting for next race_control start")


def _do_time_expiry():
    """Timer callback: auto-end a time-limited race when race_end_time is reached."""
    global _end_timer
    _end_timer = None
    if race.state == 'Running':
        race.end()
        publish_race_state()
        logger.info(f"Race {race.race_id} ended by time expiry")


def _schedule_end_timer():
    """Start the time-expiry timer if this race has a race_end_time."""
    global _end_timer
    if _end_timer and _end_timer.is_alive():
        _end_timer.cancel()
        _end_timer = None
    if race.race_end_time:
        delay = race.race_end_time - time.time()
        if delay > 0:
            _end_timer = threading.Timer(delay, _do_time_expiry)
            _end_timer.daemon = True
            _end_timer.start()
            logger.info(f"Race end timer set for {delay:.1f}s")


def _do_lights_out():
    """Timer callback: fires lights out, transitions race to Running."""
    global pending_race_cache, prev_crossing_ns
    race.start()
    prev_crossing_ns = [time.time_ns() - min_lap_time_ns - 1 for _ in range(6)]
    _schedule_end_timer()
    publish_race_state()
    pending_race_cache = fetch_pending_race()


def _cancel_start_timers():
    """Cancel any pending start-light/lights-out timers."""
    global _light_timers
    for t in _light_timers:
        if t.is_alive():
            t.cancel()
    _light_timers = []


def _set_start_lights(n):
    """Return a timer callback that lights the Nth start light and publishes state."""
    def _cb():
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
    timers = [
        threading.Timer(light_interval * i, _set_start_lights(i)) for i in range(1, 6)
    ]
    hold = random.uniform(lights_out_hold_min, lights_out_hold_max)
    lights_out_at = light_interval * 5 + hold
    timers.append(threading.Timer(lights_out_at, _do_lights_out))
    for t in timers:
        t.daemon = True
        t.start()
    _light_timers = timers
    logger.info(
        f"Race {race.race_id} armed — 5 lights at {light_interval:.1f}s spacing, "
        f"lights out at t+{lights_out_at:.1f}s"
    )


def handle_race_control(data: dict):
    """Process a race_control command from any client (browser, button box, etc.)."""
    global pending_race_cache, prev_crossing_ns, _end_timer
    command = data.get('command')
    logger.info(f"race_control: {command}")

    if command == 'arm':
        race_id = data.get('race_id')
        target_laps = data.get('target_laps', 20)

        _cancel_start_timers()
        if _end_timer and _end_timer.is_alive():
            _end_timer.cancel()
            _end_timer = None

        if pending_race_cache and pending_race_cache.get('race_id') == race_id:
            pending = pending_race_cache
        else:
            pending = fetch_pending_race()

        if not pending:
            logger.error("Cannot arm: failed to load pending race from API")
            return

        race.load_lineup(
            pending['race_id'], pending.get('race_number', 0), target_laps,
            pending['lane_assignments'], pending.get('count_first_crossing', False),
            session_type=pending.get('session_type', 'Points'),
            race_duration_seconds=pending.get('race_duration_seconds'),
            session_drivers=pending.get('session_drivers', []),
        )
        race.arm()
        publish_race_state()

        _schedule_start_sequence()

    elif command == 'start':
        race_id = data.get('race_id')
        target_laps = data.get('target_laps', 20)

        if _end_timer and _end_timer.is_alive():
            _end_timer.cancel()
            _end_timer = None

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

        race.load_lineup(
            pending['race_id'], pending.get('race_number', 0), target_laps,
            pending['lane_assignments'], pending.get('count_first_crossing', False),
            session_type=pending.get('session_type', 'Points'),
            race_duration_seconds=pending.get('race_duration_seconds'),
            session_drivers=pending.get('session_drivers', []),
        )
        race.start()
        # Reset hardware crossing times so no phantom laps bleed across race start
        prev_crossing_ns = [time.time_ns() - min_lap_time_ns - 1 for _ in range(6)]
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
            race.load_lineup(
                fresh['race_id'], fresh.get('race_number', 0), 20,
                fresh['lane_assignments'], fresh.get('count_first_crossing', False),
                session_type=fresh.get('session_type', 'Points'),
                race_duration_seconds=fresh.get('race_duration_seconds'),
                session_drivers=fresh.get('session_drivers', []),
            )
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

    elif command == 'pause':
        race.pause()
        publish_race_state()

    elif command == 'resume':
        race.resume()
        publish_race_state()

    elif command == 'end':
        _cancel_start_timers()
        if _end_timer and _end_timer.is_alive():
            _end_timer.cancel()
            _end_timer = None
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
    try:
        data = json.loads(msg.payload.decode('utf-8', 'ignore'))
        if msg.topic == 'car_timestamp':
            handle_car_timestamp(data)
        elif msg.topic == 'race_control':
            handle_race_control(data)
    except Exception as e:
        logger.error(f"Error handling {msg.topic}: {e}", exc_info=True)


def on_connect(_client, _userdata, _flags, _reason_code, _properties):
    _client.subscribe('car_timestamp')
    _client.subscribe('race_control')
    logger.info("Connected to MQTT broker")

    # Load pending race on startup so race state is available immediately
    global pending_race_cache
    pending = fetch_pending_race()
    if pending:
        pending_race_cache = pending
        race.load_lineup(
            pending['race_id'], pending.get('race_number', 0), 20,
            pending['lane_assignments'], pending.get('count_first_crossing', False),
            session_type=pending.get('session_type', 'Points'),
            race_duration_seconds=pending.get('race_duration_seconds'),
            session_drivers=pending.get('session_drivers', []),
        )
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
