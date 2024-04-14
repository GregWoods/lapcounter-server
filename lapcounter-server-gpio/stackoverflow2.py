# Testable on Raspberry Pi by connecting a jumper cable between pins 16 and 22, 
#   which will allow it to send a signal from one pin to another, which 
#   will call the callback, and allow the queueing of the stop_loop coroutine 
#   in response to the GPIO event.
# See: https://raspberrypi.stackexchange.com/questions/54514/implement-a-gpio-function-with-a-callback-calling-a-asyncio-method

import asyncio
import RPi.GPIO as GPIO

LOOP_IN = 16
LOOP_OUT = 22

@asyncio.coroutine
def delayed_raise_signal():
    yield from asyncio.sleep(1)

    GPIO.output(LOOP_OUT, GPIO.HIGH)

@asyncio.coroutine
def stop_loop():
    yield from asyncio.sleep(1)

    print('Stopping Event Loop')
    asyncio.get_event_loop().stop()

def gpio_event_on_loop_thread():
    asyncio.async(stop_loop())

def setup():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(LOOP_IN, GPIO.IN)
    GPIO.setup(LOOP_OUT, GPIO.OUT)
    GPIO.output(LOOP_OUT, GPIO.LOW)

    def on_gpio_event(channel):
        print('Rising event detected')
        loop.call_soon_threadsafe(gpio_event_on_loop_thread)

    loop = asyncio.get_event_loop()
    GPIO.add_event_detect(LOOP_IN, GPIO.RISING, callback=on_gpio_event)

    asyncio.async(delayed_raise_signal())

if __name__ == '__main__':
    setup()
    asyncio.get_event_loop().run_forever()
    GPIO.cleanup()
