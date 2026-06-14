import os
import json
import logging
import time
import paho.mqtt.client as mqtt
import psycopg2
import psycopg2.extras

MQTT_HOST = os.environ.get('MQTT_HOSTNAME', 'mosquitto')
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
DB_HOST = os.environ.get('DB_HOST', 'database')
DB_PORT = int(os.environ.get('DB_PORT', 5432))
DB_USER = os.environ.get('DB_USER', 'lap')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'lap')
DB_DATABASE = os.environ.get('DB_DATABASE', 'lapcounter_server')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

_conn = None


def get_conn():
    global _conn
    if _conn is not None and not _conn.closed:
        return _conn
    _conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        dbname=DB_DATABASE
    )
    log.info("DB connection established")
    return _conn


def wait_for_db():
    while True:
        try:
            get_conn()
            return
        except Exception as e:
            log.warning("DB not ready (%s), retrying in 5s", e)
            time.sleep(5)


def _reset_conn():
    global _conn
    try:
        if _conn:
            _conn.close()
    except Exception:
        pass
    _conn = None


def on_driver_lap(payload: dict):
    """Persist one authoritative counted lap published by lapdata. The race manager
    has already filtered idle/non-running crossings and the discarded start-line
    crossing, so we record this verbatim — no race logic is re-derived here."""
    race_id = payload.get('race_id')
    driver_id = payload.get('driver_id')
    lap_number = payload.get('lap_number')
    lap_time = payload.get('lap_time')
    if race_id is None or driver_id is None or lap_time is None:
        log.warning("Ignoring driver_lap with missing fields: %s", payload)
        return

    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, fastest_lap_time FROM driver_races WHERE race_id=%s AND driver_id=%s",
                (race_id, driver_id)
            )
            dr = cur.fetchone()
            if not dr:
                log.warning("No driver_race for race %s driver %s", race_id, driver_id)
                return

            cur.execute(
                "INSERT INTO driver_laps (driver_race_id, lap_time) VALUES (%s, %s)",
                (dr['id'], lap_time)
            )

            current_fastest = dr['fastest_lap_time']
            new_fastest = (
                lap_time if (current_fastest is None or lap_time < float(current_fastest))
                else current_fastest
            )
            cur.execute(
                "UPDATE driver_races SET laps_completed=%s, last_lap_time=%s, fastest_lap_time=%s WHERE id=%s",
                (lap_number, lap_time, new_fastest, dr['id'])
            )
        conn.commit()
        log.info("Race %s driver %s: lap %s in %.3fs", race_id, driver_id, lap_number, lap_time)
    except Exception as e:
        log.error("Error persisting lap: %s", e)
        _reset_conn()


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if msg.topic == 'driver_lap':
            on_driver_lap(payload)
    except json.JSONDecodeError:
        log.warning("Could not parse MQTT message: %s", msg.payload)
    except Exception as e:
        log.error("Unexpected error in on_message: %s", e)


def on_connect(client, userdata, flags, reason_code, properties):
    log.info("Connected to MQTT broker (rc=%s)", reason_code)
    client.subscribe('driver_lap')
    log.info("Subscribed to 'driver_lap'")


def main():
    log.info("DB Writer starting — waiting for database")
    wait_for_db()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    log.info("Connecting to MQTT at %s:%d", MQTT_HOST, MQTT_PORT)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == '__main__':
    main()
