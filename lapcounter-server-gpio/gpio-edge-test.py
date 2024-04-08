import RPi.GPIO as GPIO
import asyncio

pwr_btn_pin = 3
GPIO.setmode(GPIO.BCM)
GPIO.setup(pwr_btn_pin, GPIO.IN)
GPIO.add_event_detect(pwr_btn_pin, GPIO.RISING, callback=lambda _ : print("button pressed!"))

async def main():
    while True:
        await asyncio.sleep(0.1)

asyncio.run(main())

