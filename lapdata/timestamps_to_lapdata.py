import time
import os
import json
import logging
import urllib.request
import urllib.error
import paho.mqtt.client as mqtt
from race_manager import RaceManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
api_url = os.getenv('API_URL', 'http://api:8000')
min_lap_time_ns = int(os.getenv('MINIMUM_LAP_TIME', '2')) * 1_000_000_000

race = RaceManager()
pending_race_cache: dict | None = None

# Hardware-level: last crossing time per lane (nanoseconds) for phantom-trigger filtering
prev_crossing_ns = [time.time_ns() - min_lap_time_ns - 1 for _ in range(6)]


def fetch_pending_race() -> dict | None:
    """Fetch pending race lineup from the API. Returns parsed JSON or None on failure."""
    try:
        url = f"{api_url}/races/pending/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        logger.error(f"API unavailable when fetching pending race: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch pending race: {e}")
    return None


def handle_car_timestamp(data: dict):
    """Process a raw hardware crossing. Filters phantoms, publishes lap, updates race state."""
    lane = data['car']
    idx = lane - 1

    now_ns = time.time_ns()
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

    if race.on_lap(lane, crossing_time):
        publish_race_state()
        if race.state == 'Finished':
            logger.info("Race finished — waiting for next race_control start")


def handle_race_control(data: dict):
    """Process a race_control command from any client (browser, button box, etc.)."""
    global pending_race_cache, prev_crossing_ns
    command = data.get('command')
    logger.info(f"race_control: {command}")

    if command == 'start':
        race_id = data.get('race_id')
        target_laps = data.get('target_laps', 20)

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

        race.load_lineup(pending['race_id'], pending.get('race_number', 0), target_laps,
                         pending['lane_assignments'], pending.get('count_first_crossing', False))
        race.start()
        # Reset hardware crossing times so no phantom laps bleed across race start
        prev_crossing_ns = [time.time_ns() - min_lap_time_ns - 1 for _ in range(6)]
        publish_race_state()

        # Pre-fetch the next pending race (creates it in DB if needed)
        pending_race_cache = fetch_pending_race()

    elif command == 'prepare':
        # Refresh the lineup cache at green-flag time, before POST /races/N/start
        # can advance the pending race to N+1. This fixes stale cache when lanes
        # are changed after LapData's startup fetch.
        race_id = data.get('race_id')
        fresh = fetch_pending_race()
        if fresh:
            pending_race_cache = fresh
            logger.info(f"Lineup cached for race {fresh.get('race_id')} on prepare (requested {race_id})")
        else:
            logger.warning("prepare: failed to refresh lineup cache")

    elif command == 'pause':
        race.pause()
        publish_race_state()

    elif command == 'resume':
        race.resume()
        publish_race_state()

    elif command == 'end':
        race.end()
        publish_race_state()

    else:
        logger.warning(f"Unknown race_control command: {command}")


def publish_race_state():
    client.publish('race_state', json.dumps(race.to_dict()))


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
        race.load_lineup(pending['race_id'], pending.get('race_number', 0), 20,
                         pending['lane_assignments'], pending.get('count_first_crossing', False))
        publish_race_state()
    else:
        logger.warning("No pending race found on startup — waiting for race_control start")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_hostname)
client.loop_forever()
