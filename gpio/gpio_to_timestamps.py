# Non-docker, local Ubuntu, run with the following commands:
#
#   export LANE_NUMBER=1
#   export MQTT_HOSTNAME=mosquitto
#   sudo -E python3 gpio_to_timestamps.py
#
# Note: -E is needed to pass the environment variables to sudo

import json
import time
import os
import paho.mqtt.client as mqtt     #uses >= 2.0.0
import sys
import RPi.GPIO as GPIO             # actually uses the lgpio library for compativility with newer Linux kernels
from layer1_clock import CLOCK, HEARTBEAT_INTERVAL_S, MQTT_CLOCK_TOPIC, counter_ms

# LANE_NUMBER starts from 1. 
#   It is passed in as an environment variable in the docker compose file. 
lane_idx = int(os.getenv('LANE_NUMBER')) - 1
print(f"LANE_NUMBER: {lane_idx}")

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
print(f"MQTT_HOSTNAME: {mqtt_hostname}")

MQTT_TIMESTAMP_TOPIC = "car_timestamp"

# setup GPIO pin constants
lanes = [{
    "SELECTED": 2,
    "HSHAKE": 4,
    "CARCODE1": 27,
    "CARCODE2": 22,
    "CARCODE3": 17
}, {
    "SELECTED": 19,
    "HSHAKE": 13,
    "CARCODE1": 6,
    "CARCODE2": 5,
    "CARCODE3": 26
}]

lane = lanes[lane_idx]
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(True)
GPIO.setup(lane["SELECTED"], GPIO.IN)
GPIO.setup(lane["HSHAKE"], GPIO.OUT)
GPIO.setup(lane["CARCODE1"], GPIO.IN)
GPIO.setup(lane["CARCODE2"], GPIO.IN)
GPIO.setup(lane["CARCODE3"], GPIO.IN)
GPIO.output(lane["HSHAKE"], False)
GPIO.output(lane["HSHAKE"], True)
GPIO.output(lane["HSHAKE"], False)
GPIO.output(lane["HSHAKE"], True)

client = None

def send_lap_time(car_number, crossing_counter_ms):
    lapdata = {"car": car_number, "lane": lane_idx + 1,
               "counter_ms": crossing_counter_ms, "clock": CLOCK}
    lapjson = json.dumps(lapdata)
    print(lapjson)
    client.publish(MQTT_TIMESTAMP_TOPIC, payload=lapjson)

def handshake_end(_):
    GPIO.output(lane["HSHAKE"], False)
    flag1 = GPIO.input(lane["SELECTED"])
    while flag1 != 1:
        flag1 = GPIO.input(lane["SELECTED"])
    GPIO.output(lane["HSHAKE"], True)

def car_detected(_):
    # Stamped here, first thing: this is when the car actually crossed. Reading the
    # car-code pins and the MQTT publish below both take time, and none of it may end
    # up in a lap.
    crossing_counter_ms = counter_ms()
    # send car id 1-6
    car_number = 1
    if GPIO.input(lane["CARCODE1"]): car_number += 1
    if GPIO.input(lane["CARCODE2"]): car_number += 2
    if GPIO.input(lane["CARCODE3"]): car_number += 4
    send_lap_time(car_number, crossing_counter_ms)
    handshake_end(lane)

# utilises a new thread to handle the GPIO event detection
print(f"lane selected GPIO: {lane['SELECTED']}")
GPIO.add_event_detect(lane["SELECTED"], GPIO.FALLING, callback=car_detected)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(mqtt_hostname)
# create a new thread to handle the network loop. Also handles reconnecting
client.loop_start()

# Keep the program running, and while we're here publish the clock heartbeat: a bare
# reading of the counter for lapdata to pair with its own arrival time. Lap 1 is timed
# from lights-out, which happens before any car has crossed, so crossings alone would
# leave lapdata with nothing to anchor against at exactly the moment it needs one.
#
# Both lane containers publish this. They carry the same clock id and the same counter,
# so the samples are interchangeable and lapdata just gets twice as many.
while True:
    time.sleep(HEARTBEAT_INTERVAL_S)
    client.publish(MQTT_CLOCK_TOPIC,
                   payload=json.dumps({"clock": CLOCK, "counter_ms": counter_ms()}))
