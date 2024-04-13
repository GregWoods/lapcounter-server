# Run with the following
#   . ./setenv.sh
#   sudo -E python3 generate_raw_lap_data_from_gpio.py
# 
#   -E is needed to pass the environment variables to the sudo command

import asyncio
import json
import random
import time
import sys
import os
import aiomqtt
#import paho.mqtt as mqtt
from dotenv import load_dotenv
import sys
import RPi.GPIO as GPIO
import datetime
import time


# Load dev environment variables. We don't override existing variables set 
#   using docker compose --env-file which is used in production

#load_dotenv('../.env.local', override=False)   #only needed if we are running the script outside of the container

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
print(f"MQTT_HOSTNAME: {mqtt_hostname}")

MINIMUM_LAP_TIME = float(os.getenv('MINIMUM_LAP_TIME'))
if MINIMUM_LAP_TIME is None:
    MINIMUM_LAP_TIME = 3.0
print(f"MINIMUM_LAP_TIME: ${MINIMUM_LAP_TIME}")

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

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(True)  # ????

# setup GPIO pins
for lane in lanes:
    GPIO.setup(lane["SELECTED"], GPIO.IN)
    GPIO.setup(lane["HSHAKE"], GPIO.OUT)
    GPIO.setup(lane["CARCODE1"], GPIO.IN)
    GPIO.setup(lane["CARCODE2"], GPIO.IN)
    GPIO.setup(lane["CARCODE3"], GPIO.IN)
    GPIO.output(lane["HSHAKE"], False)
    GPIO.output(lane["HSHAKE"], True)
    GPIO.output(lane["HSHAKE"], False)
    GPIO.output(lane["HSHAKE"], True)

# setup previous_times array for all 6 cars
now = datetime.datetime.now().timestamp()
# up to 8 cars theoretically possible using the current 3bit data from the GPIO. 
#   We will use index 1-6 to match car number, and ignore index 0 and 7
previous_times = [now, now, now, now, now, now, now, now]


client = aiomqtt.Client(mqtt_hostname)

async def send_lap_time(car_number, crossing_time):
    lap_time = crossing_time.timestamp() - previous_times[car_number]
    if lap_time > MINIMUM_LAP_TIME:
        lapdata = {"car": car_number, "laptime": lap_time}
        lapjson = json.dumps(lapdata)
        print(lapjson)
        previous_times[car_number] = crossing_time.timestamp()

        # publish lap time to mqtt
        try:
        #async with aiomqtt.Client(mqtt_hostname) as client:
            await client.publish("lap", payload=lapjson)
        except aiomqtt.MqttError:
            print(f"Connection lost; Reconnecting in 1 second ...")
            await asyncio.sleep(1)        
        


def handshake_end(lane):
    GPIO.output(lane["HSHAKE"], False)
    flag1 = GPIO.input(lane["SELECTED"])
    while flag1 != 1:
        flag1 = GPIO.input(lane["SELECTED"])
    GPIO.output(lane["HSHAKE"], True)


async def car_detected(lane):
    crossing_time = datetime.now()
    car_number = 0
    if GPIO.input(lane["CARCODE1"]): car_number += 1
    if GPIO.input(lane["CARCODE2"]): car_number += 2
    if GPIO.input(lane["CARCODE3"]): car_number += 4
    await send_lap_time(car_number, crossing_time)
    handshake_end(lane)


async def lane1_car_detected():
    await car_detected(lanes[0])
    
async def lane2_car_detected():
    await car_detected(lanes[1])



GPIO.add_event_detect(lanes[0]["SELECTED"], GPIO.RISING, callback=lane1_car_detected)
GPIO.add_event_detect(lanes[1]["SELECTED"], GPIO.RISING, callback=lane2_car_detected)    


async def schedule_tasks():
    while True:
        try:
            async with client:
                # Do nothing here, the interrupts handle everything GPIO related
                await asyncio.sleep(0.01)
        # add conection lost exception handling
        except aiomqtt.MqttError:
            print(f"Connection lost; Reconnecting in 1 second ...")
            await asyncio.sleep(1)

# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
