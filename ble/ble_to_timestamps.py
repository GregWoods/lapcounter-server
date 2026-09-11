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

# Per car-ID (index 0..5 = car 1..6): last-seen raw StartFinish1/2 values, so a
# notification only turns into a crossing when one of them actually changed —
# the powerbase renotifies the full slot state on any field change, not just laps.
_last_start_finish = [[None, None] for _ in range(6)]

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

                while client.is_connected:
                    await asyncio.sleep(1)
                logger.warning("BLE connection dropped.")
        except Exception as e:
            logger.error(f"BLE error: {e}")

        logger.info(f"Retrying in {reconnect_delay}s...")
        await asyncio.sleep(reconnect_delay)


mqtt_client.connect(mqtt_hostname)
# create a new thread to handle the network loop. Also handles reconnecting
mqtt_client.loop_start()

asyncio.run(run())
