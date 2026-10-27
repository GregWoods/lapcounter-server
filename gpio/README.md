# Standalone Scalextric Digital Lap Counter - GPIO Data Acquisition Layer

## Create and push a cross platform build.

```build-and-push-gpio.ps1```

The commands in this script can be run individually and modified, if for example, during development you didn't want to push an interim
build to DockerHub, replace `--push` with `--load`.

The script builds one image, which uses the actual gpio pins on a Raspberry Pi, for:

* `linux/arm/v7` for 32 bit Raspberry Pi OS running on the Pi Zero 2 W or Pi 3A+
* `linux/arm64/v8` for 64 bit Raspberry Pi OS running on a 1Gb+ Pi 3 or later


## Run it without a Pi (dev)

The same `gpio_to_timestamps.py` runs against a fake `RPi.GPIO` (`mock_rpi_gpio.py`), one
container per lane as on the Pi, fed crossings by `mock_track.py` (#101). Only one Layer 1
may run, so stop the dev default first:

```
docker compose -f ../compose.dev.yaml stop mocked-ble
docker compose -f ../compose.dev.yaml --profile mocked-gpio up -d --build mock-track mocked-gpio-1 mocked-gpio-2
```

The `mock_*.py` files are kept out of the image by `.dockerignore`; the dev services
bind-mount this folder to get them.
