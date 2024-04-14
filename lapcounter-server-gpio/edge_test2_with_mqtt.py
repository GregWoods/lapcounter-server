#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time
import threading
import asyncio
import aiomqtt
import paho.mqtt as mqtt

pwr_btn_gpio = 3
mqtt_hostname = "10.0.1.188"

GPIO.setmode(GPIO.BCM)
GPIO.setup(pwr_btn_gpio, GPIO.IN)

def handle(channel):
    movement = GPIO.input(pwr_btn_gpio)
    if movement:
        print("Press")
    else:
        print("Release")

print ("Setting up event detect")
worked = False
while not worked:
    # keep trying to set up event detect based on suggestion in 
    # https://www.raspberrypi.org/forums/viewtopic.php?f=32&t=129015&p=874227#p874227
    worked = True
    try:
        GPIO.add_event_detect(pwr_btn_gpio, GPIO.BOTH, handle)
    except RuntimeError:
        worked = False

print("We are running!")  # This never prints, never gets out of above while loop


async def main():
    client = aiomqtt.Client(mqtt_hostname)
    while True:
        try:
            async with client:
                # Do nothing here, the interrupts handle everything GPIO related
                await asyncio.sleep(0.01)
        # add conection lost exception handling
        except aiomqtt.MqttError:
            print(f"Connection lost; Reconnecting...")
            await asyncio.sleep(0.2)


asyncio.run(main())
