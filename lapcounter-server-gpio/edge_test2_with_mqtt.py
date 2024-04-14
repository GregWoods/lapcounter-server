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

loop = None
client = aiomqtt.Client(mqtt_hostname)

#we use asyncio's loop directly so that both button handler and mqtt client
#   can be run in the same thread
def handle(self):

    if loop is None:
        print("ERROR: loop is None")
        return

    btn_down = GPIO.input(pwr_btn_gpio)
    if btn_down:
        print("Press")
        print(client)
    else:
        print("Release")
    #try:
    loop.call_soon_threadsafe(lambda x: self.client.publish("lap", "test message"))

    #await client.publish("lap", "test message")
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


print("start forever loop. Is this code run?")

async def main():
    while True:
        await asyncio.sleep(0.2)

asyncio.run(main())

print("EXIT and cleanup")
GPIO.cleanup()
