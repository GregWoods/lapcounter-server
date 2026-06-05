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
    command = data.get('command')
    logger.info(f"race_control: {command}")

    if command == 'start':
        pending = fetch_pending_race()
        if not pending:
            logger.error("Cannot start: failed to load pending race from API")
            return
        target_laps = data.get('target_laps', 20)
        race.load_lineup(pending['race_id'], target_laps, pending['lane_assignments'])
        race.start()
        # Reset hardware crossing times so no phantom laps bleed across race start
        global prev_crossing_ns
        prev_crossing_ns = [time.time_ns() - min_lap_time_ns - 1 for _ in range(6)]
        publish_race_state()

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
    pending = fetch_pending_race()
    if pending:
        race.load_lineup(pending['race_id'], 20, pending['lane_assignments'])
        publish_race_state()
    else:
        logger.warning("No pending race found on startup — waiting for race_control start")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_hostname)
client.loop_forever()
