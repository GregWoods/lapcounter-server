# Dev-only Layer 1 lane: the real, unmodified gpio_to_timestamps.py running against a
# fake RPi.GPIO (mock_rpi_gpio.py), fed crossings by mock_track.py. Needs no Pi. One
# container per lane, exactly as on the Pi, with LANE_NUMBER and MQTT_HOSTNAME set.
#
# gpio_to_timestamps.py has no __main__ guard and sets up its pins at import, so the fake
# must be in sys.modules before it runs. It carries no mock hooks: real or fake is decided
# only by the container's command.

import runpy
import sys
import types

import mock_rpi_gpio

rpi = types.ModuleType('RPi')
rpi.GPIO = mock_rpi_gpio
sys.modules['RPi'] = rpi
sys.modules['RPi.GPIO'] = mock_rpi_gpio

mock_rpi_gpio.start()
runpy.run_path('gpio_to_timestamps.py', run_name='__main__')
