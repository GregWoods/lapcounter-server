"""The API's race_state subscriber (#79): persists the race lifecycle lapdata publishes.

Every race_state, retained and republished every 2s by lapdata, goes to
race_lifecycle.reconcile(). QoS 0 and a clean session are enough: the message is a level,
not an event, so a lost one is repaired by the next beat, and on (re)connect the broker
hands over the retained current state straight away. A DB that is down is just logged;
the next beat tries again.

⚠️ One uvicorn worker only (`fastapi run` starts one). The client id is fixed, so a second
worker would keep disconnecting the first rather than quietly writing twice.
"""
import json
import logging

import paho.mqtt.client as mqtt
from sqlmodel import Session

from race_lifecycle import reconcile

logger = logging.getLogger('uvicorn.error')

CLIENT_ID = 'api-race-state'


def _on_connect(client, _userdata, _flags, reason_code, _properties):
    logger.info(f"race_state subscriber connected to MQTT (rc={reason_code})")
    client.subscribe('race_state')


def _on_message(_client, engine, msg):
    try:
        race_state = json.loads(msg.payload.decode('utf-8', 'ignore'))
    except json.JSONDecodeError:
        logger.warning(f"race_state subscriber: unparseable message {msg.payload!r}")
        return
    try:
        with Session(engine) as dbsession:
            reconcile(dbsession, race_state)
    except Exception as e:
        logger.error(f"race_state subscriber: reconcile failed, retrying on the next beat: {e}")


def start(engine, host: str, port: int) -> mqtt.Client:
    """Connect in the background and return the client, for stop(). Never blocks: an API
    that starts before the broker keeps serving and connects when it can."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID,
                         clean_session=True, userdata=engine)
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.connect_async(host, port, keepalive=30)
    client.loop_start()
    logger.info(f"race_state subscriber connecting to {host}:{port}")
    return client


def stop(client: mqtt.Client):
    """Disconnect cleanly. Under `fastapi dev` this runs on every reload, and a client left
    behind with the same id would fight the new one."""
    client.disconnect()
    client.loop_stop()
