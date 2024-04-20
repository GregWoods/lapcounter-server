# Non-docker, run with the following commands
#   . ./setenv.sh
#   sudo -E python3 generate_raw_lap_data_from_gpio.py
# 
#   -E is needed to pass the environment variables to sudo

import json
import time
import os
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import sys
import RPi.GPIO as GPIO

# LANE_NUMBER starts from 1
lane_idx = int(os.getenv('LANE_NUMBER')) - 1
print(f"LANE_NUMBER: {lane_idx}")

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
print(f"MQTT_HOSTNAME: {mqtt_hostname}")

# setup GPIO pin constants
pwr_btn_gpio = 3
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

GPIO.setup(pwr_btn_gpio, GPIO.IN)

client = None

def send_lap_time(car_number, crossing_time):
    lapdata = {"car": car_number, "timestamp": crossing_time, "lane": lane_idx + 1}
    lapjson = json.dumps(lapdata)
    print(lapjson)
    client.publish("lap", payload=lapjson)

def handshake_end(_):
    GPIO.output(lane["HSHAKE"], False)
    flag1 = GPIO.input(lane["SELECTED"])
    while flag1 != 1:
        flag1 = GPIO.input(lane["SELECTED"])
    GPIO.output(lane["HSHAKE"], True)

def car_detected(_):
    print("car detected")
    crossing_time = time.time_ns()
    # send car id 1-6
    car_number = 1
    if GPIO.input(lane["CARCODE1"]): car_number += 1
    if GPIO.input(lane["CARCODE2"]): car_number += 2
    if GPIO.input(lane["CARCODE3"]): car_number += 4
    print(f"car number: {car_number}")
    print(f"crossing time: {crossing_time}")
    send_lap_time(car_number, crossing_time)
    handshake_end(lane)

# to be removed once the system is stable
def send_test_mqtt(_):
    print("send_test_mqtt")
    print(f"client: {client}")
    client.publish("lap", payload="test")

# utilises a new thread to handle the GPIO event detection
print(f"lane selected GPIO: {lane['SELECTED']}")
GPIO.add_event_detect(lane["SELECTED"], GPIO.FALLING, callback=car_detected)

# temporary: detect button press for testing
GPIO.add_event_detect(pwr_btn_gpio, GPIO.RISING, callback=send_test_mqtt)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(mqtt_hostname)
# create a new thread to handle the network loop. Also handles reconnecting
client.loop_start()

while True:
    time.sleep(0.001)

client.disconnect()
client.loop_stop()
