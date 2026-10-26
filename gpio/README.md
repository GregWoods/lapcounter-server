# Standalone Scalextric Digital Lap Counter - GPIO Data Acquisition Layer

## Create and push a cross platform build.

```build-and-push-gpio.ps1```

The commands in this script can be run individually and modified, if for example, during development you didn't want to push an interim
build to DockerHub, replace `--push` with `--load`.

The script builds 2 images, one for mocked gpi data and the other which uses the actual gpio pins on a Raspberry Pi.

Note that we build for 3 architectures:

* `linux/amd64`for local use (run from WSL2 or Docker) using the mocked gpio 
* `linux/arm/v7` for 32 bit Raspberry Pi OS running on the Pi Zero 2 W or Pi 3A+
* `linux/arm64/v8` for 64 bit Raspberry Pi OS running on a 1Gb+ Pi 3 or later


## Run it locally in Docker

Correctly set up environment variables are needed for any of these containers to run. So instead of using `docker run` directly, we run can run the container using docker compose.

```docker compose -f ../compose.dev.yaml up --build mocked-gpio```


## Can GPIO tell whether the sensor board is plugged in? (#116)

`sensor_presence_check.py` answers this on the race Pi. It samples every input pin of both lanes, under pull-down, pull-up and no pull, once with the board plugged in and once unplugged. Today the pins have no pull resistor, so an unplugged `SELECTED` pin floats and can raise phantom crossings with random car IDs.

Copy the script to the Pi and run it inside the gpio image (privileged, already has RPi.GPIO). The lane containers hold the pins, so stop them first:

```
scp gpio/sensor_presence_check.py <pi>:~/
ssh <pi>
docker stop gpio-1 gpio-2
docker run --rm -it --privileged -v $PWD/sensor_presence_check.py:/app/check.py \
    gregkwoods/lapcounter-server-gpio:latest python check.py
docker start gpio-1 gpio-2
```

Keep cars off the line while it samples (3 s per pin per pull setting). It prompts you to plug the board in, then to unplug it. For each lane it reports:

* **DETECTABLE**: the board drives `SELECTED` high when idle. With a pull-down, GPIO can report `sensors_connected` from the pin, and an unplugged pin can no longer raise phantom edges.
* **NOT_DRIVEN_HIGH**: the board only pulls `SELECTED` low (open collector), so idle and unplugged look the same. Presence has to be proved by a crossing instead (a car pushed over the line during setup).
* **INCONCLUSIVE**: something moved during sampling (usually a car). Run it again.

It also reports how many phantom crossings the floating, unpulled pin produced. The analysis is unit-tested in `test_sensor_presence_check.py`.
