# Non-docker, run with the following commands
#   . ./setenv.sh
#   sudo -E python3 generate_raw_lap_data_from_gpio.py
# 
#   -E is needed to pass the environment variables to the sudo command

import json
import random
import time
import sys
import os
import asyncio
import aiomqtt
import paho.mqtt as mqtt
from dotenv import load_dotenv
import sys
import RPi.GPIO as GPIO
import datetime
import time

# LANE_NUMBER starts from 1, lane_number is 0 based
lane_number = int(os.getenv('LANE_NUMBER')) - 1

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

lane = lanes[lane_number]
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(True)  # ????
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
    lapdata = {"car": car_number, "timestamp": crossing_time, "lane": lane_number + 1}
    lapjson = json.dumps(lapdata)
    print(lapjson)
    try:
        client.publish("lap", payload=lapjson)
    except mqtt.MqttError:
        print(f"send_lap_time: Connection lost")
        # reconnection is done in main loop


def handshake_end():
    GPIO.output(lane["HSHAKE"], False)
    flag1 = GPIO.input(lane["SELECTED"])
    while flag1 != 1:
        flag1 = GPIO.input(lane["SELECTED"])
    GPIO.output(lane["HSHAKE"], True)


def car_detected():
    crossing_time = datetime.now()
    car_number = 0
    if GPIO.input(lane["CARCODE1"]): car_number += 1
    if GPIO.input(lane["CARCODE2"]): car_number += 2
    if GPIO.input(lane["CARCODE3"]): car_number += 4
    send_lap_time(car_number, crossing_time)
    handshake_end(lane)

GPIO.add_event_detect(lane["SELECTED"], GPIO.RISING, callback=car_detected)

#while True:
#    client = mqtt.Client(mqtt_hostname)
#    time.sleep(0.1)



#async def send_message(driver):
#    async with aiomqtt.Client(os.getenv('MQTT_HOSTNAME')) as client:
#        while True:
#            driver.generateLap()
#            await asyncio.sleep(max(0, driver.nextLapAt - time.time()))            
#            driver.dbg()    
#            lapdata = {"type": "lap", "car": driver.driverNumber, "time": driver.nextLapAt}
#            lapjson = json.dumps(lapdata)
#            await client.publish("lap", payload=lapjson)
#            print(lapdata)


# Create a task for each driver
#async def schedule_tasks():
#    async with asyncio.TaskGroup() as tg:
#        for driver in drivers:
#            tg.create_task(send_message(driver))

async def main():
    while True:
        try:
            async with client:
                # Do nothing here, the interrupts handle everything GPIO related
                await asyncio.sleep(0.01)
        # add conection lost exception handling
        except aiomqtt.MqttError:
            print(f"Connection lost; Reconnecting...")
            await asyncio.sleep(0.2)

client = aiomqtt.Client(mqtt_hostname)
asyncio.run(main())
