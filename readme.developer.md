# LapCounter-Server - Developer Readme

See readme in the individual sub-project folders for instructions on how to build and run locally, and how to push updated docker images to dockerhub.

## Quick Start

Local development using docker

```
docker compose -f compose.dev.yaml up -build
```

React works with hot module reloading. 

```
http://localhost:8088
```

Suggest using the browser's developer tools to set up a new custom device which runs at a resolution of 1920x1080. Whilst other resolutions may work, there has been a lot of hardcoded css to make it work well at this resolution.

## Project Structure

This project is build in a very modular way, making use of several Docker containers. Some, such as the MQTT server are well known public projects.
The lap counter code itself is split amongst several containers. These are outlined below.


## Layer 1 - gpio


This layer only runs on a Raspberry Pi, it cannot be run on your developer machine. It uses the raspberry Pi's GPIO to read car ID data as each car crosses the start finish line.
To keep this code really simple, in production, typically 2 of these containers are run from this image, one per track lane. 

Example data, published to the MQTT host, under topic: **car_timestamp**

```{"car": 2, "timestamp": 1715270252241772183, "lane": 1}```

In production, this step runs one container per track lane (usually 2).

During development, the mocked version automatically produces data for 2 lanes.



## Layer 2 - lapdata

Subscribes to the "car_timestamp" topic on the MQTT server, and transforms it into more useful lap data. 

This data is then published to another MQTT queue, with topic "lap".

Example data (using the example input above), published to the MQTT host, under topic: **lap**


```{"type": "lap", "car": 2, "time": 1715270252.2429936, "lapTime": 17.1683136}```


## Layer 3 - web

This is a Python API running on Flask.
In production this will run in an nginx server


## Layer 4 - react

This is a simple container running nginx to serve the React app.
It does not run whilst in development, since we use the vite build-in server to serve the React front end on port 5173.
In production, these files will be served from the static folder of the Flask app running on nginx.




# Why this Project?

The goal is that multiple clients can subscribe to this data. In theory, we could have multiple web browsers connected over WiFi. Each driver could have their own custom display on their phones (3D printed throttle-top phone holder anyone?) showing their personal lap times and relative positions to the driver in front and behind. We could also have additional client hardware displaying other useful info around the track. Hardware start lights, green, yellow, red flag illuminated boards could all be set up with a simple connection to a web page served from one of the containers running on the Pi. Old mobile phones could be put to use, as could ESP32 based gadgets. There are lots of possibilities.

For example, we could have the standard leaderboard shown on a large screen TV. But we could have as many of these as we wanted. Instead of running the browser in the Pi itself (which prevents us using fancy CSS animations, due to lack of processing grunt), we use separate laptops, PCs and other Raspi's to connect to the server. 

The current ZoomRoom system has the back end python code sending very basic data. It knows nothing about the state of the race. The start, stop, pausing of the race, as well as management of the drivers and cars, are all done in the browser (pure JS for the original ZoomRoom code, and React JS in my re-write). My proposal will move much of that logic into the backend Python containers. This will mean we can permanently store race stats in a database for later analysis, and stats for whole race meet, and maybe even the whole season. It also means a browser refresh doesn't kill the current race.

None of this is tied to the ZoomRoom hardware... it just proved to be a convenient platform for experimenting. Any car ID sensors which can attach to a Raspberry Pi would work. Standalone sensors would work, but they would need network access and have the ability to publish MQTT messages. (RTC clock syncing would be needed for any sensor which sends time-critical data)


# Why Use Docker?

I realise the Docker approach could sound pretty repulsive to anyone who works directly with Assembly or C/C++/Rust on a microcontroller. I've previously experimented with all 3 languages on a mix of AVR, PIC and 32 bit Arm Cortex CPUs, and still feel the Docker approach has adavantages in terms of speed of development and modularity. Obviously it will take some testing to determine if the weight of an entire Linux OS, plus Docker, plus containers can handle it all. In this system, remember that the Pi itself is not reading Car LED pulses directly. That part has been offloaded onto a couple of PIC microcontrollers.

The timing critical part is making sure the signal from the microcontrollers is not missed, delayed or colliding with the signal from a second car in the other lane. Manually driving 2 cars over the Start/Finish line hasn't got it to fail, but that is a pretty inconclusive reliability test. I think I'd need to build hardware emitters to place over the lane sensors which can emulate 2 cars crossing the line at precisely the same time (and then with increasing microsecond delays between them). The Python code is using edge detection interrupts rather than polling, so I'd expect it to be pretty responsive. Of course, having multiple Raspi CPU cores running in the Gigahertz range will help too.

In the end, for me, whilst I would like 100% reliability even for the 1 in a million edge case... for the kind of social race meets with friends and kids, my main motivation is the ability to easily add features to the race management system. 

In the meantime. All the code is public. It is just a series of experiments at the moment. 



# Development Methodology

Docker all the way!

### Not recommended
We can run any python scripts interactively using "py scriptname", but for production usage, we build into a docker image. This image will then run as a container on the Raspi3A server




# Running on the Raspi

```
cd ~/lapcounter-server
sudo docker compose --env-file .env.docker --profile production up  --pull always
# see the compose file for the different profiles
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




# Testing Mosquitto

check which of these 2 methods is easiest

1.

* Using mqttx (cli) installed on my local machine, I can subscribe to the mqtt events to see what is happening
    * mqttx sub -h <mqtt_broker_ip_address> -t "car_timestamp"
    * mqttx sub -h <mqtt_broker_ip_address> -t "lap"


2.

* In WSL Ubuntu
* apt install mosquitto-clients
* see: https://mosquitto.org/man/mosquitto_sub-1.html
* mosquitto_sub -h localhost -p 1883 -t lap
* In a separate WSL Ubuntu tab...
* mosquitto_pub -h localhost -p 1883 -t lap -m 1212121.333
* We can use the above sub command to keep an eye on data published by lapcounter-server-gpio when real slots cars cross the start/finish line, or we can monitor sample data published by lapcounter-server-lapdata
