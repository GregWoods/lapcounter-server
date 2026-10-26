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

# What lapdata's race manager can make of a crossing (race_manager.CROSSING_OUTCOMES), and
# what migration 008's CHECK constraint allows. Kept in step with both by hand.
OUTCOMES = ('counted', 'start_line', 'yellow_flag', 'baseline', 'too_short')


def get_conn():
    global _conn
    if _conn is not None and not _conn.closed:
        return _conn
    _conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        dbname=DB_DATABASE, connect_timeout=5
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


# A database that can't be reached, as opposed to one that rejects this particular row.
# Only these leave a message unacked for redelivery: anything else would be rejected
# again on every redelivery and block the queue behind it.
DB_UNAVAILABLE = (psycopg2.OperationalError, psycopg2.InterfaceError)


def on_driver_lap(payload: dict):
    """Persist one crossing published by lapdata, as the race manager judged it. Its
    `outcome` is 'counted' for a real lap; anything else ('start_line', 'yellow_flag',
    'baseline', 'too_short') is a void crossing, stored for traceability with no lap time and left
    out of the driver_races aggregates (#86). We record it verbatim — no race logic is
    re-derived here.

    Idempotent (#77): driver_lap arrives at least once, so a crossing already stored is
    skipped (driver_laps is unique on driver_race_id, clock, counter_ms), and the
    driver_races aggregates are recomputed from the stored rows rather than taken from
    the message. Raises DB_UNAVAILABLE if the database can't be reached, so the caller
    leaves the message unacked; returns normally once the message is dealt with,
    including when it is dropped."""
    race_id = payload.get('race_id')
    driver_id = payload.get('driver_id')
    lap_number = payload.get('lap_number')
    lap_time = payload.get('lap_time')
    # A lapdata older than #86 sends counted laps only, without an outcome.
    outcome = payload.get('outcome', 'counted')
    counted = outcome == 'counted'
    if race_id is None or driver_id is None or (counted and lap_time is None):
        log.warning("Ignoring driver_lap with missing fields: %s", payload)
        return
    # Said here, not left to the CHECK constraint: a rejected INSERT only surfaces as a
    # generic "Error persisting lap", and the crossing is lost either way.
    if outcome not in OUTCOMES:
        log.error("Dropping driver_lap with unknown outcome %r (lapdata newer than "
                  "dbwriter, or a migration missing?): %s", outcome, payload)
        return
    if payload.get('clock') is None or payload.get('counter_ms') is None:
        # Still stored, but a NULL never matches the unique key, so a redelivery of this
        # one would be stored twice.
        log.warning("driver_lap without clock/counter_ms can't be deduplicated: %s", payload)

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM driver_races WHERE race_id=%s AND driver_id=%s",
                (race_id, driver_id)
            )
            dr = cur.fetchone()
            if not dr:
                log.warning("No driver_race for race %s driver %s", race_id, driver_id)
                # The SELECT above already opened a transaction (psycopg2 is not
                # autocommit) — returning without ending it left the connection idle in
                # transaction indefinitely, holding whatever locks it acquired, until (if
                # ever) a later successful lap happened to commit it along the way. Bit
                # us for real: a stray driver_lap for a race_id/driver_id with no
                # matching driver_races row left this connection idle in transaction for
                # 12+ minutes, blocking an unrelated `DROP TABLE` elsewhere.
                conn.rollback()
                return

            cur.execute(
                # created_at explicitly, so this doesn't depend on the table having a DB
                # default — a create_all-built schema once had none and lost every lap (#84).
                # A void crossing is recorded exactly like a lap, with no lap_time. The
                # provenance columns (#27) are what lets a disputed lap be re-checked.
                "INSERT INTO driver_laps (driver_race_id, lap_time, outcome, clock, counter_ms, "
                "crossed_at, created_at) "
                "VALUES (%s, %s, %s, %s, %s, to_timestamp(%s), NOW()) "
                "ON CONFLICT (driver_race_id, clock, counter_ms) DO NOTHING",
                (dr['id'], lap_time if counted else None, outcome,
                 payload.get('clock'), payload.get('counter_ms'), payload.get('crossed_at'))
            )
            inserted = cur.rowcount == 1

            # From the rows, never the message: that makes it idempotent, repairs itself
            # when a lost lap is redelivered late, and doesn't care about delivery order.
            # Run for void crossings too, so there is one code path. laps_completed is
            # raw — penalties are subtracted only when results are built (#83).
            cur.execute(
                "UPDATE driver_races SET "
                "laps_completed = (SELECT COUNT(*) FROM driver_laps "
                "    WHERE driver_race_id = %(id)s AND outcome = 'counted'), "
                "fastest_lap_time = (SELECT MIN(lap_time) FROM driver_laps "
                "    WHERE driver_race_id = %(id)s AND outcome = 'counted'), "
                "last_lap_time = (SELECT lap_time FROM driver_laps "
                "    WHERE driver_race_id = %(id)s AND outcome = 'counted' "
                "    ORDER BY crossed_at DESC NULLS LAST, id DESC LIMIT 1) "
                "WHERE id = %(id)s",
                {'id': dr['id']}
            )
        conn.commit()
    except DB_UNAVAILABLE:
        _reset_conn()
        raise
    except psycopg2.Error as e:
        # This row was rejected; retrying it won't help.
        log.error("Dropping driver_lap the database rejected (%s): %s", e, payload)
        conn.rollback()
        return

    if not inserted:
        log.info("Race %s driver %s: %s crossing at %s/%s already recorded (redelivery)",
                 race_id, driver_id, outcome, payload.get('clock'), payload.get('counter_ms'))
    elif counted:
        log.info("Race %s driver %s: lap %s in %.3fs", race_id, driver_id, lap_number, lap_time)
    else:
        log.info("Race %s driver %s: %s crossing recorded", race_id, driver_id, outcome)


def on_driver_penalty(payload: dict):
    """Persist a penalty lapdata's race manager already applied live (#88), so
    build_session_results() can fold it into final standings. race_penalties is the one
    penalty record: the void crossing that incurred it is in driver_laps, but nothing
    reads penalties from there. The crossing's clock/counter_ms are stored alongside, for
    traceability only.

    Idempotent (#94), with the same delivery handling as on_driver_lap: driver_penalty
    arrives at least once, and race_penalties is unique on the penalty_id lapdata minted
    when it applied the penalty, so a redelivery is skipped rather than charged twice.
    Raises DB_UNAVAILABLE if the database can't be reached, so the caller leaves the
    message unacked; returns normally once the message is dealt with."""
    race_id = payload.get('race_id')
    driver_id = payload.get('driver_id')
    penalty_type = payload.get('penalty_type')
    amount = payload.get('amount')
    reason = payload.get('reason')
    penalty_id = payload.get('penalty_id')
    if None in (race_id, driver_id, penalty_type, amount, reason):
        log.warning("Ignoring driver_penalty with missing fields: %s", payload)
        return
    if penalty_id is None:
        # A lapdata older than #94. Still stored, but a NULL never matches the unique
        # key, so a redelivery of this one would be charged twice.
        log.warning("driver_penalty without penalty_id can't be deduplicated: %s", payload)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                # issued_at is lapdata's stamp from the payload, never NOW(): a
                # redelivery is the same message, written later.
                "INSERT INTO race_penalties (race_id, driver_id, penalty_type, amount, reason, "
                "penalty_id, issued_at, clock, counter_ms, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s, NOW()) "
                "ON CONFLICT (penalty_id) DO NOTHING",
                (race_id, driver_id, penalty_type, amount, reason, penalty_id,
                 payload.get('issued_at'), payload.get('clock'), payload.get('counter_ms'))
            )
            inserted = cur.rowcount == 1
        conn.commit()
    except DB_UNAVAILABLE:
        _reset_conn()
        raise
    except psycopg2.Error as e:
        # This row was rejected; retrying it won't help.
        log.error("Dropping driver_penalty the database rejected (%s): %s", e, payload)
        conn.rollback()
        return

    if inserted:
        log.info("Race %s driver %s: %s penalty of %s (%s) recorded",
                 race_id, driver_id, penalty_type, amount, reason)
    else:
        log.info("Race %s driver %s: penalty %s already recorded (redelivery)",
                 race_id, driver_id, penalty_id)


# Set when the database stopped answering mid-connection. Every message after that is
# left unacked too, until we have disconnected, waited for the database and reconnected.
_awaiting_redelivery = False


def on_message(client, userdata, msg):
    """With manual_ack, a QoS 1 driver_lap or driver_penalty is acked only once it is
    committed (or deliberately dropped). If the database is unreachable it is left unacked and we
    disconnect: the broker resends unacked messages only when a persistent session
    reconnects — there is no ack timeout — and 20 unacked ones would stop it sending
    anything at all (max_inflight_messages). main() reconnects once the database answers."""
    global _awaiting_redelivery
    if _awaiting_redelivery:
        return
    try:
        payload = json.loads(msg.payload.decode())
        if msg.topic == 'driver_lap':
            on_driver_lap(payload)
        elif msg.topic == 'driver_penalty':
            on_driver_penalty(payload)
    except json.JSONDecodeError:
        log.warning("Could not parse MQTT message: %s", msg.payload)
    except DB_UNAVAILABLE as e:
        log.error("Database unavailable (%s) — leaving %s unacked and disconnecting; the "
                  "broker resends it once the database is back", e, msg.topic)
        _awaiting_redelivery = True
        client.disconnect()
        return
    except Exception as e:
        log.error("Unexpected error in on_message: %s", e)
        _reset_conn()
    client.ack(msg.mid, msg.qos)


def on_connect(client, userdata, flags, reason_code, properties):
    log.info("Connected to MQTT broker (rc=%s, session present=%s)",
             reason_code, flags.session_present)
    # QoS 1 into a persistent session (#77, #94): the broker queues both while we're
    # away and resends any we hadn't acked. Safe because both tables have a dedup key:
    # driver_laps on the crossing, race_penalties on penalty_id.
    client.subscribe('driver_lap', qos=1)
    client.subscribe('driver_penalty', qos=1)
    log.info("Subscribed to 'driver_lap' and 'driver_penalty' (QoS 1)")


def main():
    global _awaiting_redelivery
    # A fixed client id and clean_session=False make the broker keep our subscriptions
    # and queue driver_lap/driver_penalty while we're disconnected (for persistent_client_expiration,
    # in mosquitto.conf). The id must be unique to this one service.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='dbwriter',
                         clean_session=False, manual_ack=True)
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        log.info("Waiting for database")
        wait_for_db()
        _awaiting_redelivery = False
        log.info("Connecting to MQTT at %s:%d", MQTT_HOST, MQTT_PORT)
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        # Reconnects by itself if the broker goes away; returns only when on_message
        # disconnects because the database did.
        client.loop_forever()


if __name__ == '__main__':
    main()
