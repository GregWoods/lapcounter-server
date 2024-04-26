# Testable on Raspberry Pi by connecting a jumper cable between pins 16 and 22, 
#   which will allow it to send a signal from one pin to another, which 
#   will call the callback, and allow the queueing of the stop_loop coroutine 
#   in response to the GPIO event.
# See: https://raspberrypi.stackexchange.com/questions/54514/implement-a-gpio-function-with-a-callback-calling-a-asyncio-method

import asyncio
import RPi.GPIO as GPIO
import aiomqtt

async def publish_message():
    # unsure if/why this extra step needed
    #create client here for now
    client = aiomqtt.Client("10.0.1.188")
    client.publish("lap", "test")

def gpio_event_on_loop_thread():
    asyncio.ensure_future(publish_message())

def setup():
    loop = asyncio.get_event_loop()

    def on_gpio_event(channel):
        print('Rising event detected')
        # on_gpio_event is called from a gpio event thread,
        #   but the callback which makes the mqtt call needs to be called from the main thread
        #   so we can utilise asyncio features
        loop.call_soon_threadsafe(gpio_event_on_loop_thread)

    pwr_btn_gpio = 3
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pwr_btn_gpio, GPIO.IN)
    GPIO.add_event_detect(pwr_btn_gpio, GPIO.RISING, callback=on_gpio_event)

if __name__ == '__main__':
    setup()
    asyncio.get_event_loop().run_forever()
    GPIO.cleanup()
