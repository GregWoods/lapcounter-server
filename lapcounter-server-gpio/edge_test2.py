#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time
import threading

pwr_btn_gpio = 3
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

while True:
    time.sleep(1e6)
