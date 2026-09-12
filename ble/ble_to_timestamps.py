# Layer 1 alternative to gpio_to_timestamps.py: reads lap crossings straight from a
# Scalextric ARC Pro powerbase over Bluetooth LE instead of two GPIO finish-line
# sensors, and republishes them on the same car_timestamp contract. One container
# replaces both gpio/gpio_to_timestamps.py instances (BLE reports all 6 digital
# car IDs over one connection, gpio needs one process per physical lane sensor).
#
#   export MQTT_HOSTNAME=mosquitto
#   export BLE_ADDRESS=AA:BB:CC:DD:EE:FF   # optional, skips the discovery scan
#   python3 ble_to_timestamps.py
#
# Requires BlueZ's D-Bus socket to be reachable from the container
# (bind-mount /var/run/dbus) and a working Bluetooth adapter on the host.

import asyncio
import json
import logging
import os
import time

import paho.mqtt.client as mqtt      # uses >= 2.0.0
from bleak import BleakClient, BleakScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
logger.info(f"MQTT_HOSTNAME: {mqtt_hostname}")

# BLE_ADDRESS skips the discovery scan and connects to a known powerbase directly —
# the recommended mode on a dedicated race Pi, since scanning by name needs broader
# Bluetooth capabilities than connecting to a known address.
device_name = os.getenv('BLE_DEVICE_NAME', 'Scalextric ARC')
device_address = os.getenv('BLE_ADDRESS')
scan_timeout = float(os.getenv('BLE_SCAN_TIMEOUT', '10'))
reconnect_delay = float(os.getenv('BLE_RECONNECT_DELAY', '5'))

MQTT_TIMESTAMP_TOPIC = "car_timestamp"

# Scalextric ARC "slot" GATT characteristic (notify-only). Confirmed against
# github.com/RazManager/ScalextricArcBleProtocolExplorer, which implements
# Scalextric's official ARC BLE protocol doc. Notification payload (18 bytes,
# little-endian):
#   byte[0]      packet sequence
#   byte[1]      CarId, 1-6 — already the digital car ID, no CARCODE bit-decode needed
#   byte[2:6]    TimestampStartFinish1 (uint32) — physical lane 1 sensor
#   byte[6:10]   TimestampStartFinish2 (uint32) — physical lane 2 sensor
#   byte[10:18]  pitlane timestamps — unused, this project has no pit lane feature
SLOT_CHARACTERISTIC_UUID = "00003b0b-0000-1000-8000-00805f9b34fb"

# Command characteristic (write-only, 20 bytes): byte 0 selects one of these overall
# powerbase states (power + whether Slot characteristic timestamps tick/halt/reset);
# bytes 1-19 are per-car power/rumble/brake/KERS overrides, unused so far — see
# ble/reference/Scalextric_ARC_BLE_Protocol.md for the full table.
COMMAND_CHARACTERISTIC_UUID = "00003b0a-0000-1000-8000-00805f9b34fb"
NO_POWER_TIMER_STOPPED = 0
NO_POWER_TIMER_TICKING = 1
POWER_ON_RACE_TRIGGER = 2
POWER_ON_RACING = 3
POWER_ON_TIMER_HALT = 4
NO_POWER_REBOOT_PIC18 = 5

# Per car-ID (index 0..5 = car 1..6): last-seen raw StartFinish1/2 values, so a
# notification only turns into a crossing when one of them actually changed —
# the powerbase renotifies the full slot state on any field change, not just laps.
_last_start_finish = [[None, None] for _ in range(6)]

# Set once BLE is connected (inside run()), cleared on disconnect. Lets
# handle_race_control(), which runs on paho's own MQTT thread, hand a GATT write
# off to bleak's asyncio client safely via run_coroutine_threadsafe (see
# send_command() below) — bleak's client isn't thread-safe to call directly.
_bleak_client: BleakClient | None = None
_ble_loop: asyncio.AbstractEventLoop | None = None

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def publish_crossing(car_number: int, lane: int):
    payload = {"car": car_number, "timestamp": time.time_ns(), "lane": lane}
    mqtt_client.publish(MQTT_TIMESTAMP_TOPIC, payload=json.dumps(payload))
    logger.info(f"car_timestamp: car={car_number} lane={lane}")


def handle_slot_notification(_sender, data: bytearray):
    car_id = data[1]
    if not (1 <= car_id <= 6):
        return
    idx = car_id - 1
    timestamp1 = int.from_bytes(data[2:6], 'little')
    timestamp2 = int.from_bytes(data[6:10], 'little')

    previous1, previous2 = _last_start_finish[idx]
    if timestamp1 and timestamp1 != previous1:
        _last_start_finish[idx][0] = timestamp1
        publish_crossing(car_id, 1)
    if timestamp2 and timestamp2 != previous2:
        _last_start_finish[idx][1] = timestamp2
        publish_crossing(car_id, 2)


async def _write_command_async(command: int):
    if not (_bleak_client and _bleak_client.is_connected):
        logger.warning(f"Cannot write command {command}: BLE not connected")
        return
    payload = bytes([command]) + bytes(19)  # power/rumble/brake/KERS bytes unused so far
    await _bleak_client.write_gatt_char(COMMAND_CHARACTERISTIC_UUID, payload)
    logger.info(f"Command characteristic <- {command}")


def send_command(command: int):
    """Thread-safe entry point for scheduling a Command characteristic write from
    outside bleak's asyncio loop (e.g. paho's on_message thread)."""
    if _ble_loop is None:
        logger.warning(f"Cannot write command {command}: BLE not connected")
        return
    asyncio.run_coroutine_threadsafe(_write_command_async(command), _ble_loop)


def handle_race_control(data: dict):
    """Translate a race_control command into a Command characteristic write.

    Every transition currently maps to POWER_ON_RACING — Layer 1 stays dumb and
    lapdata's race manager is the sole authority on what counts as a real lap, so
    this only needs to keep the powerbase powered and ticking, matching what GPIO
    always did (it has no ability to cut power at all). Differentiating pause/end/
    yellow-flag states (POWER_ON_RACE_TRIGGER, POWER_ON_TIMER_HALT) is future work.

    Note 'arm' fires several seconds before the actual lights-out "go" (lapdata
    runs the start-light countdown internally, with no race_control message at the
    precise go instant) — see handle_race_state() below for the write that lands
    exactly then.
    """
    command = data.get('command')
    if command in ('prepare', 'arm', 'start', 'pause', 'resume', 'end'):
        send_command(POWER_ON_RACING)
    elif command != 'status':
        logger.warning(f"Unknown race_control command: {command}")


# Last state seen in a race_state message, so handle_race_state() can detect the
# NotStarted/ArmedForStart -> Running edge instead of rewriting on every message
# (race_state is republished on every single lap crossing).
_last_seen_race_state: str | None = None


def handle_race_state(data: dict):
    """Redundant, precisely-timed write: lapdata publishes race_state the instant
    the start lights go out (race.start() sets race_start_time then publishes),
    so reacting to the Running transition here lands a POWER_ON_RACING write right
    at "go" — belt-and-braces alongside the earlier 'arm' write in
    handle_race_control(), covering e.g. a BLE reconnect during the countdown."""
    global _last_seen_race_state
    state = data.get('state')
    if state == 'Running' and _last_seen_race_state != 'Running':
        send_command(POWER_ON_RACING)
    _last_seen_race_state = state


def on_mqtt_message(_client, _userdata, msg):
    try:
        data = json.loads(msg.payload.decode('utf-8', 'ignore'))
        if msg.topic == 'race_control':
            handle_race_control(data)
        elif msg.topic == 'race_state':
            handle_race_state(data)
    except Exception as e:
        logger.error(f"Error handling {msg.topic}: {e}", exc_info=True)


def on_mqtt_connect(client, _userdata, _flags, _reason_code, _properties):
    client.subscribe('race_control')
    client.subscribe('race_state')


async def find_device_address() -> str:
    if device_address:
        return device_address

    logger.info(f"Scanning for BLE device named '{device_name}'...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _adv: d.name == device_name,
        timeout=scan_timeout,
    )
    if device is None:
        raise TimeoutError(f"No BLE device named '{device_name}' found within {scan_timeout}s")
    return device.address


async def run():
    global _bleak_client, _ble_loop
    while True:
        try:
            address = await find_device_address()
            logger.info(f"Connecting to {address}...")
            async with BleakClient(address) as client:
                logger.info("Connected to Scalextric ARC powerbase.")
                for car in _last_start_finish:
                    car[0] = None
                    car[1] = None

                await client.start_notify(SLOT_CHARACTERISTIC_UUID, handle_slot_notification)
                logger.info("Subscribed to slot notifications — waiting for crossings.")

                # Publishing race_control writes is only meaningful once connected —
                # exposing the client/loop here is what lets send_command() (called
                # from paho's thread) reach this asyncio loop via
                # run_coroutine_threadsafe.
                _bleak_client = client
                _ble_loop = asyncio.get_running_loop()
                await _write_command_async(POWER_ON_RACING)

                while client.is_connected:
                    await asyncio.sleep(1)
                logger.warning("BLE connection dropped.")
        except Exception as e:
            logger.error(f"BLE error: {e}")
        finally:
            _bleak_client = None
            _ble_loop = None

        logger.info(f"Retrying in {reconnect_delay}s...")
        await asyncio.sleep(reconnect_delay)


mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_message = on_mqtt_message
mqtt_client.connect(mqtt_hostname)
# create a new thread to handle the network loop. Also handles reconnecting
mqtt_client.loop_start()

asyncio.run(run())
