# Must run under sudo
#   or we get error: RuntimeError: Failed to add edge detection

import RPi.GPIO as GPIO
import asyncio

pwr_btn_gpio = 3
GPIO.setmode(GPIO.BCM)
GPIO.setup(pwr_btn_gpio, GPIO.IN)

GPIO.add_event_detect(pwr_btn_gpio, GPIO.RISING, callback=lambda _ : print(f"GPIO {pwr_btn_gpio} RISING"))

async def main():
    while True:
        await asyncio.sleep(0.1)

asyncio.run(main())

