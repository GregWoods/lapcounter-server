# Dev-only Layer 1: the real, unmodified ble_to_timestamps.py running against a simulated
# powerbase (mock_powerbase.py) through a fake bleak (mock_bleak.py). Needs no Bluetooth
# adapter. See docs/mocked-ble-plan.md.
#
# The dev default Layer 1, so a plain `docker compose -f compose.dev.yaml up` runs it.
#   docker compose -f compose.dev.yaml restart mocked-ble     # after editing ./ble
#   docker exec mosquitto mosquitto_sub -t mock/powerbase     # watch power and laps
#
# Env (all optional):
#   MOCK_CARS=6                        simulated cars, 0-6
#   MOCK_SLOT_INTERVAL_MS=50           one Slot packet per interval, round-robin over 6 IDs
#   MOCK_DISCONNECT_POWER=hold         hold|off|on: track power after a BLE drop (HW-07)
#   MOCK_DROP_EVERY_S=                 disconnect this long after every connect
#   MOCK_WRITE_FAIL_RATE=0             0-1 chance a Command write fails (exercises the retry)
#   MOCK_NO_COMMAND_CHARACTERISTIC=    true: behave like an ARC One, rejecting every write

import asyncio
import collections
import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt

import ble_to_timestamps as ble
import mock_bleak
from mock_powerbase import SimulatedPowerbase

logger = logging.getLogger('mock_ble')

# Dev-only observability. Nothing in lapdata, React or the API may subscribe to this:
# it is not part of the contract, and a subscriber would be layers 2+ knowing the hardware.
MOCK_POWERBASE_TOPIC = 'mock/powerbase'
SNAPSHOT_INTERVAL_S = 1.0
FOREIGN_TIMESTAMP_LOG_INTERVAL_S = 30.0


def _env(name: str, default: str) -> str:
    return os.getenv(name) or default


# ----------------------------------------------------- swap bleak for the fakes
# run() and find_device_address() look these names up at call time, so replacing the
# module globals is enough. ble_to_timestamps.py itself carries no mock hooks.
ble.BleakClient = mock_bleak.FakeBleakClient
ble.BleakScanner = mock_bleak.FakeBleakScanner

powerbase = SimulatedPowerbase(
    cars=int(_env('MOCK_CARS', '6')),
    disconnect_power=_env('MOCK_DISCONNECT_POWER', 'hold'),
)
drop_every = _env('MOCK_DROP_EVERY_S', '')
mock_bleak.configure(
    powerbase,
    faults=mock_bleak.Faults(
        drop_every_s=float(drop_every) if drop_every else None,
        write_fail_rate=float(_env('MOCK_WRITE_FAIL_RATE', '0')),
        no_command_characteristic=_env('MOCK_NO_COMMAND_CHARACTERISTIC', '').lower() in ('1', 'true', 'yes'),
    ),
    slot_interval_s=float(_env('MOCK_SLOT_INTERVAL_MS', '50')) / 1000,
)

# ------------------------------------------------------- double Layer 1 guard
# Remember what ble publishes on car_timestamp, so anything else arriving there can be
# recognised as a second Layer 1 (almost always mocked-gpio left running), which means
# every lap is being counted twice.
_own_payloads = collections.deque(maxlen=500)
_own_payloads_lock = threading.Lock()
_real_publish = ble.mqtt_client.publish


def _recording_publish(topic, payload=None, *args, **kwargs):
    if topic == ble.MQTT_TIMESTAMP_TOPIC:
        with _own_payloads_lock:
            _own_payloads.append(payload)
    return _real_publish(topic, payload, *args, **kwargs)


ble.mqtt_client.publish = _recording_publish

# A separate client for the guard and mock/powerbase, so ble's own client keeps exactly
# its production subscriptions and callbacks.
observer = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
_foreign_count = 0
_foreign_logged_at = 0.0


def on_observer_connect(client, _userdata, _flags, _reason_code, _properties):
    client.subscribe(ble.MQTT_TIMESTAMP_TOPIC)


def on_observer_message(_client, _userdata, msg):
    global _foreign_count, _foreign_logged_at
    payload = msg.payload.decode('utf-8', 'ignore')
    with _own_payloads_lock:
        if payload in _own_payloads:
            return
    _foreign_count += 1
    now = time.monotonic()
    if now - _foreign_logged_at >= FOREIGN_TIMESTAMP_LOG_INTERVAL_S:
        _foreign_logged_at = now
        logger.error(f"Another Layer 1 is publishing car_timestamp ({_foreign_count} foreign so far, "
                     f"latest {payload}) — every lap is being double-counted. "
                     f"Stop it: docker compose -f compose.dev.yaml stop mocked-gpio")


observer.on_connect = on_observer_connect
observer.on_message = on_observer_message


# ----------------------------------------------------------- mock/powerbase
def publish_snapshot():
    """Only ever call on bleak's loop (the powerbase listener and the snapshot task).
    The powerbase isn't locked: advance() from a second thread could count a crossing
    twice. The topic is retained and republished every second, so a freshly connected
    observer needs no immediate publish."""
    observer.publish(MOCK_POWERBASE_TOPIC, json.dumps(powerbase.snapshot()), retain=True)


async def publish_snapshots_forever():
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_S)
        try:
            publish_snapshot()
        except Exception:
            logger.exception('Publishing mock/powerbase failed')


async def main():
    powerbase.add_listener(publish_snapshot)
    await asyncio.gather(ble.run(), publish_snapshots_forever())


if __name__ == '__main__':
    # Same startup as ble_to_timestamps' __main__ block, plus the observer.
    ble.mqtt_client.connect(ble.mqtt_hostname)
    ble.mqtt_client.loop_start()
    observer.connect(ble.mqtt_hostname)
    observer.loop_start()

    asyncio.run(main())
