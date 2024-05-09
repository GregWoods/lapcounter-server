# LapCounter-Server - Developer Readme

See readme in the individual sub-project folders for instructions on how to build and run locally, and how to push updated docker images to dockerhub.


## Project Structure

This project is build in a very modular way, making use of several Docker containers. Some, such as the MQTT server are well known public projects.
The lap counter code itself is split amongst several containers. These are outlined below.


## Layer 1 - lapcounter-server-gpio


This layer only runs on a Raspberry Pi, it cannot be run on your developer machine. It uses the raspberry Pi's GPIO to read car ID data as each car crosses the start finish line.
To keep this code really simple, in production, multiple containers are run from this image, one per track lane. 

Example data, published to the MQTT host, under topic: **car_timestamp**

```{"car": 2, "timestamp": 1715270252241772183, "lane": 1}```

In production, this step runs one container per track lane (usually 2).

During development, the mocked version automatically produces data for 2 lanes.



## Layer 2 - lapcounter-server-lapdata

Subscribes to the "car_timestamp" topic on the MQTT server, and transforms it into more useful lap data. 

This data is then published to another MQTT queue, with topic "lap".

Example data (using the example input above), published to the MQTT host, under topic: **lap**


```{"type": "lap", "car": 2, "time": 1715270252.2429936, "lapTime": 17.1683136}```



[2024-05-09] Currently this service converts times from nanoseconds to seconds, and adds the calculated lap time (currently unused). Later versions of "lapdata" will supply lap data for all drivers in one hit, dramatically simplifying the React code.

Overview

The goal is that multiple clients can subscribe to this data. In theory, we could have multiple web browsers connected over WiFi. Each driver could have their own custom display on their phones (3D printed throttle-top phone holder anyone?) showing their personal lap times and relative positions to the driver in front and behind.

The current ZoomRoom system has the back end python code sending very basic data. It knows nothing about the state of the race. The start, stop, pausing of the race, as well as management of the drivers and cars, are all done in the browser (pure JS for the original ZoomRoom code, and React JS in my re-write). My proposal will move much of that logic into the backend Python containers. This will mean we can permanently store race stats in a database. We could also have additional clients displaying other useful info around the track. Hardware start lights, green, yellow, red flag illuminated boards could all be set up with a simple connection to a web page served from one of the containers running on the Pi. Old mobile phones could be put to use, as could ESP32 based gadgets. There are lots of possibilities.

None of this is tied to the ZoomRoom hardware... it just proved to be a convenient platform for experimenting. Any car ID sensors which can attach to a Raspberry Pi would work. Standalone sensors would work, but they would need network access and have the ability to publish MQTT messages. (RTC clock syncing would be needed for any sensor which sends time-critical data)

This brings me to another advantage of using a Pi with Docker. It would already be running a web server in a Docker container. But it could also run another container acting as a wireless access point and DHCP server. This means you could have multiple trackside devices, such as the aforementioned yellow flag displays, starting lights, driver's mobile phones, all connected to the Pi. You've then created a WiFi based system which does not rely on your house WiFi setup. It would be separate to your home WiFi, self-contained and completely portable.

I realise much if this could sound pretty repulsive to anyone who works directly with Assembly or C/C++/Rust on a microcontroller. I know, as I've previously experimented with all 3 languages on a mix of AVR, PIC and 32 bit Arm Cortex CPUs. Obviously it will take some testing to determine if the weight of an entire Linux OS, plus Docker, plus containers inside Docker can handle it all. In this system, remember that the Pi itself is not reading Car LED pulses directly. That part has been offloaded onto a coupl eof PIC microcontrollers.

The timing critical part is making sure the signal from the microcontrollers is not missed, delayed or colliding with the signal from a second car in the other lane. Manually driving 2 cars over the Start/Finish line hasn't got it to fail, but that is a pretty inconclusive reliability test. I think I'd need to build hardware emitters to place over the lane sensors which can emulate 2 cars crossing the line at precisely the same time (and then with increasing microsecond delays between them). The Python code is using edge detection interrupts rather than polling, so I'd expect it to be pretty responsive. Of course, having multiple Raspi CPU cores running in the Gigahertz range will help too.

In the end, for me, whilst I would like 100% reliability even for the 1 in a million edge case... for the kind of social race meets with friends and kids, my main motivation is the ability to easily add features to the race management system. 

In the meantime. All the code is public. It is just a series of experiments at the moment. I will add an Open-Source with Attribution type licence.



# Future Enhancements

[TODO]

This project is takes the hardware and ideas from ZoomRoom's FSR Lap counter, and completely reworks it so that all the processing is done at the server end instead of in the browser. The goal is to allow multiple clients to consume race data. 

For example, we could have the standard leaderboard shown on a large screen TV. But we could have as many of these as we wanted. Instead of running the browser in the Pi itself (which prevents us using fancy CSS animations, due to lack of processing grunt), we use separate laptops, PCs and other Raspi's to connect to the server. 

The server can also serve up different types of pages. For example, each driver could have their own page which they can see on their phone. It could show the last few laps laptime, and other info specific to them.

This server based approach allows us to more easily store lap data for later analysis and historical records.

It is designed to work with ZoomRoom's hardware, which is a piece of Scalextric track housing a photodiode in each lane connected to a Raspberry Pi 3A with a daughterboard containing a circuit to read and interpret the the carId from the 2 track lanes. 

The implementation will be done in a containerised manner using messgae queues. Although it may seem an overkill approach, once the initial config is setup, it should make individual components of the system easy to work on. For example, we could use one server to read GPIO data from the photodiodes and publish the raw data (timestamp and carid) to a queue. Another service could read that queue and calculate current race data such as driver positions, laptimes, and publish to another queue. This queue could feed the web service which displays the results on the main screen or driver's phone screens. The same queue could feed another service which perisistently stores lap and race data.

# Components

**Current State**

## lapcounter-server-gpio

### gpio_output_test.py
Proof of concept. Doesn't read carid data. Instead reads button presses on the Raspi an publishes using MQTT

### generate_raw_lap_data_from_gpio.py
The first step. This code reads the carId from the Raspberry Pis GPIO pins and publishes that to a queue with minimal processing. It should be fast. Running in a separate container should ensure it is non-blocking to other processes.

Initial version works for a single lane. A second instance can be run for lane 2. It is hoped (and confirmed with testing) that the OS and Docker will provide more than enough resources to be able to read both lanes at the same time and have both post to the MQTT server.

Because generate_raw_lap_data_from_gpio.py does not know about other instance, it does not perform any lap time calculations, it simply logs the system timestamp and the car which crossed the line. 

Initial version uses GPIO.add_event_detect for pin chnage detection. This creates a new thread, so that the MQTT message send should not block subsequent pin reading.


## lapcounter-server-lapdata

### create_lap_data.py
creates random lap data and publishes using MQTT. Used for development.

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

se specific folder for exact commands

# Running Locally (without Docker)

makes use of .env.local


# Running on the Raspi

```
cd ~/lapcounter-server
sudo docker compose --env-file .env.docker --profile production up  --pull always
# see the compose file for the different profiles
```

# Running Locally (Docker)

```
# Pulling image
docker compose --profile test up  --pull always

# Building image
docker compose --profile test up --build
```




## Developer - Build & Push Docker Images

Once it is all working locally

* Set new version tag in build.ps1
* Build docker images and upload to dockerhub

```
> Powershell. ToDo. Convert to Bash
cd /mnt/c/Users/gregw/projects/lapcounter-server/
./build.ps1
```

Additionally
* Using mqttx (cli) installed on my local machine, I can subscribe to the mqtt events to see what is happening
    * mqttx sub -h <mqtt_broker_ip_address> -t "car_timestamp"
    * mqttx sub -h <mqtt_broker_ip_address> -t "lap"
