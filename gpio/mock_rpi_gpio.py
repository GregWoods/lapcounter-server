"""A fake RPi.GPIO: one lane's finish-line sensor board, driven over MQTT. Dev only.

mock_gpio_to_timestamps.py puts this in sys.modules as `RPi.GPIO`, so the real,
unmodified gpio_to_timestamps.py runs against it. A crossing is injected by mock_track.py
on `mock/gpio/lane<N>` as `{"car": 3}`, and this plays the board's side of it:

1. CARCODE1-3 are set from the car number (car 1 = all low, as the real script decodes);
2. SELECTED goes low, and the falling-edge callback runs on this module's own thread,
   as lgpio runs it on its own;
3. the script drops HSHAKE to acknowledge, and the board releases SELECTED, which is what
   handshake_end() spins on.

Crossings are handled one at a time, like the real board, which can't report a second
car until the first has been acknowledged.

Known difference from hardware: the crossing happens when the injection message arrives,
so the broker's few ms of jitter end up in lap times. Fine for dev.

`mock/gpio/*` is dev-only, like `mock/powerbase`: nothing above Layer 1 may subscribe.
"""
import json
import logging
import os
import threading

import paho.mqtt.client as mqtt

logger = logging.getLogger('mock_rpi_gpio')

MOCK_GPIO_TOPIC = 'mock/gpio/lane{}'

# The board's wiring, per lane. Must match `lanes` in gpio_to_timestamps.py; a mismatch
# fails at startup (add_event_detect, input, output) rather than misreading car numbers.
WIRING = [
    {'SELECTED': 2, 'HSHAKE': 4, 'CARCODE1': 27, 'CARCODE2': 22, 'CARCODE3': 17},
    {'SELECTED': 19, 'HSHAKE': 13, 'CARCODE1': 6, 'CARCODE2': 5, 'CARCODE3': 26},
]

BCM = 11
IN = 1
OUT = 0
FALLING = 32

_lane_number = int(os.getenv('LANE_NUMBER'))
_pins = WIRING[_lane_number - 1]
_levels = {pin: 1 for pin in _pins.values()}
_callback = None
_lock = threading.Lock()


def setmode(_mode):
    pass


def setwarnings(_flag):
    pass


def setup(pin, _direction):
    if pin not in _levels:
        raise ValueError(f"GPIO {pin} is not wired on lane {_lane_number}'s board")


def output(pin, value):
    if pin != _pins['HSHAKE']:
        raise ValueError(f"GPIO {pin} is not an output on lane {_lane_number}'s board")
    _levels[pin] = 1 if value else 0
    # The acknowledgement: the board releases SELECTED once HSHAKE drops.
    if not value:
        _levels[_pins['SELECTED']] = 1


def input(pin):
    return _levels[pin]


def add_event_detect(pin, edge, callback):
    global _callback
    if pin != _pins['SELECTED'] or edge != FALLING:
        raise ValueError(f"Expected a falling edge on SELECTED (GPIO {_pins['SELECTED']}), "
                         f"got GPIO {pin}: is WIRING out of step with gpio_to_timestamps.py?")
    _callback = callback


def _cross(car: int):
    code = car - 1
    with _lock:
        _levels[_pins['CARCODE1']] = code & 1
        _levels[_pins['CARCODE2']] = (code >> 1) & 1
        _levels[_pins['CARCODE3']] = (code >> 2) & 1
        _levels[_pins['SELECTED']] = 0
        if _callback is None:
            logger.warning(f"Car {car} crossed before the script registered its callback")
            _levels[_pins['SELECTED']] = 1
            return
        _callback(_pins['SELECTED'])


def _on_connect(client, _userdata, _flags, _reason_code, _properties):
    client.subscribe(MOCK_GPIO_TOPIC.format(_lane_number))


def _on_message(_client, _userdata, msg):
    try:
        car = int(json.loads(msg.payload)['car'])
    except (ValueError, KeyError, TypeError):
        logger.error(f"Bad injected crossing on {msg.topic}: {msg.payload!r}")
        return
    if not 1 <= car <= 6:
        logger.error(f"Injected car {car} is outside 1-6")
        return
    _cross(car)


def start():
    """Listen for injected crossings, on paho's own thread (the callback's thread)."""
    injector = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    injector.on_connect = _on_connect
    injector.on_message = _on_message
    injector.connect(os.getenv('MQTT_HOSTNAME'))
    injector.loop_start()
