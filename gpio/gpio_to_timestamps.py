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

def send_lap_time(car_number, crossing_time):
    lapdata = {"car": car_number, "timestamp": crossing_time, "lane": lane_idx + 1}
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
    crossing_time = time.time_ns()
    # send car id 1-6
    car_number = 1
    if GPIO.input(lane["CARCODE1"]): car_number += 1
    if GPIO.input(lane["CARCODE2"]): car_number += 2
    if GPIO.input(lane["CARCODE3"]): car_number += 4
    send_lap_time(car_number, crossing_time)
    handshake_end(lane)

# utilises a new thread to handle the GPIO event detection
print(f"lane selected GPIO: {lane['SELECTED']}")
GPIO.add_event_detect(lane["SELECTED"], GPIO.FALLING, callback=car_detected)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(mqtt_hostname)
# create a new thread to handle the network loop. Also handles reconnecting
client.loop_start()

#Just keep the program running
while True:
    time.sleep(1)
