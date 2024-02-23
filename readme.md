# Overview

This project is takes the hardware and ideas from ZoomRoom's FSR Lap counter, and completely reworks it so that all the processing is done at the server end instead of in the browser. The goal is to allow multiple clients to consume race data. 

For example, we could have the standard leaderboard shown on a large screen TV. But we could have as many of these as we wanted. Instead of running the browser in the Pi itself (which prevents us using fancy CSS animations, due to lack of processing grunt), we use separate laptops, PCs and other Raspi's to connect to the server. 

The server can also serve up different types of pages. For example, each driver could have their own page which they can see on their phone. It could show the last few laps laptime, and other info specific to them.

This server based approach allows us to more easily store lap data for later analysis and historical records.

It is designed to work with ZoomRoom's hardware, which is a piece of Scalextric track housing a photodiode in each lane connected to a Raspberry Pi 3A with a daughterboard containing a circuit to read and interpret the the carId from the 2 track lanes. 

The implementation will be done in a containerised manner using messgae queues. Although it may seem an overkill approach, once the initial config is setup, it should make individual components of the system easy to work on. For example, we could use one server to read GPIO data from the photodiodes and publish the raw data (timestamp and carid) to a queue. Another service could read that queue and calculate current race data such as driver positions, laptimes, and publish to another queue. This queue could feed the web service which displays the results on the main screen or driver's phone screens. The same queue could feed another service which perisistently stores lap and race data.

# Components

**Current State**

## lapcounter-server-gpio
gpio_output_test.py: Proof of concept. Doesn't read carid data. Instead reads button presses on the Raspi an publishes using MQTT

gpio_raw_lap_mocked.py: I think this should be removed. The functionality to create mocked lap data has been moved to the separate container: lapcounter-server-lapdata

## lapcounter-server-lapdata
create_lap_data.py: creates random lap data and publishes using MQTT. Used for development.

Publishes to the "lap" topic


## lapcounter-server-test-mqtt-latency
test_latency.py: subscribes to the published lapdata, reads the timestamp in the message and compares to the current timestamp to come up with a latency time. If this is >0.1s, we need to rethink the approach. I would hope it would be a lot less than this.

# Testing Mosquitto

* In WSL Ubuntu
* apt install mosquitto-clients
* see: https://mosquitto.org/man/mosquitto_sub-1.html
* mosquitto_sub -h localhost -p 1883 -t lap
* In a separate WSL Ubuntu tab...
* mosquitto_pub -h localhost -p 1883 -t lap -m 1212121.333
* We can use the above sub command to keep an eye on data published by lapcounter-server-gpio when real slots cars cross the start/finish line, or we can monitor sample data published by lapcounter-server-lapdata

# Development Methodology

We can run any python scripts interactively using "py scriptname", but for production usage, we build into a docker image. This image will then run as a container on the Raspi3A server

# Building a Docker Image

This example performs a cross-platform build of lapcounter-server-test-mqtt-latency and will publish versions for amd64 and Raspberry Pi 3 (arm v7)

```
docker buildx create --use     
docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-test-mqtt-latency . --push
```

# Running Locally (without Docker)

makes use of .env.local


# Running on the Raspi

```
sudo docker compose --env-file .env.docker.raspi --profile test up  --pull always
```

# Running Locally (Docker)

```
# Pulling image
docker compose --profile test up  --pull always

# Building image
docker compose --profile test up --build
```