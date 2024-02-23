import asyncio
import json
import random
import time
import sys
import os
import aiomqtt
import paho.mqtt as mqtt
from dotenv import load_dotenv
import sys
import RPi.GPIO as GPIO
import datetime


# Load dev environment variables. We don't override existing variables set using docker compose --env-file
#   which is used in production
#load_dotenv('../.env.local', override=False)   #only needed if we are running the script outside of the container
mqtt_hostname = os.getenv('MQTT_HOSTNAME')
print(mqtt_hostname)

MINIMUM_LAP_TIME = 3.0

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
GPIO.setwarnings(False)

# setup GPIO pins
for lane in lanes:
    GPIO.setup(lane["HSHAKE"], GPIO.OUT)
    GPIO.setup(lane["SELECTED"], GPIO.IN)
    GPIO.setup(lane["CARCODE1"], GPIO.IN)
    GPIO.setup(lane["CARCODE2"], GPIO.IN)
    GPIO.setup(lane["CARCODE3"], GPIO.IN)
    GPIO.output(lane["HSHAKE"], False)
    GPIO.output(lane["HSHAKE"], True)
    GPIO.output(lane["HSHAKE"], False)
    GPIO.output(lane["HSHAKE"], True)


# setup previous_times array for all 6 cars
now = datetime.now().timestamp()
# up to 8 cars theoretically possible. We will use index 1-6 to match car number
previous_times = [now, now, now, now, now, now, now, now]


# setup mqtt client
client = mqtt.Client(os.getenv('MQTT_HOSTNAME'))


async def send_lap_time(car_number, crossing_time):
    lapsed_time = crossing_time.timestamp() - previous_times[car_number]
    if lapsed_time > MINIMUM_LAP_TIME:
        lapdata = {"type": "lap", "car": car_number, "time": crossing_time.timestamp()}
        lapjson = json.dumps(lapdata)
        print(lapjson)
        previous_times[car_number] = crossing_time.timestamp()

        # publish lap time to mqtt
        try:
            async with client:
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


async def read_gpio_send_message():
    async with aiomqtt.Client(os.getenv('MQTT_HOSTNAME')) as client:
        #Set up interrupts on the "Selected" pins
        GPIO.add_event_detect(lanes[0]["SELECTED"], GPIO.RISING, callback=lane1_car_detected)
        GPIO.add_event_detect(lanes[1]["SELECTED"], GPIO.RISING, callback=lane2_car_detected)

async def schedule_tasks():
    client = aiomqtt.Client(os.getenv('MQTT_HOSTNAME'))
    GPIO.add_event_detect(lanes[0]["SELECTED"], GPIO.RISING, callback=lane1_car_detected)
    GPIO.add_event_detect(lanes[1]["SELECTED"], GPIO.RISING, callback=lane2_car_detected)    
    while True:
        try:
            async with client:
                # Set up interrupts on the "Selected" pins
                #   The clalbacks can make use of client to publish messages

        except aiomqtt.MqttError:
            print(f"Connection lost; Reconnecting in 1 second ...")
            await asyncio.sleep(1)


# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
