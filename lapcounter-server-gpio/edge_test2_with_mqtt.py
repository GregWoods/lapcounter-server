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

async def handle():
    # client is effectively a global singleton, but needs to be instantiated here
    #   because this handler runs in a different thread
    if not client:
        client = aiomqtt.Client(mqtt_hostname)

    btn_down = GPIO.input(pwr_btn_gpio)
    if btn_down:
        print("Press")
        print(client)
    else:
        print("Release")
    #try:
    await client.publish("lap", "test message")
    #except mqtt.MqttError:
    #    print(f"handle button press: Connection lost")
    #    # reconnection is done in main loop


# see https://raspberrypi.stackexchange.com/questions/54514/implement-a-gpio-function-with-a-callback-calling-a-asyncio-method
#  we sill use the asyncio event loop directly so we don't need to use async/await in the button handling callback

GPIO.setmode(GPIO.BCM)
GPIO.setup(pwr_btn_gpio, GPIO.IN)
GPIO.add_event_detect(pwr_btn_gpio, GPIO.BOTH, handle)
# run the event loop
loop = asyncio.get_event_loop()
loop.run_forever()
loop.close()

async def main():
    global client 
    
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


GPIO.cleanup()
