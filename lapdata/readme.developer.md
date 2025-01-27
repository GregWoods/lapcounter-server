# Build Instructions

## Create and Push a Cross Platform Build.

* linux/amd64 for local use (run from WSL2)
* arm/v7 for Raspberry Pi 3A

```
docker buildx build --platform linux/arm/v7,linux/arm64/v8,linux/amd64 --push -t gregkwoods/lapcounter-server-lapdata:latest .
```

## Local build and Run

docker build -f ./Dockerfile -t lapcounter-server-lapdata:latest .
docker run --env-file ../.env.local lapcounter-server-lapdata













Move all this to the global readme

# Generating a working lapcounter and Race Management System

## Step 1 - lapcounter-server-gpio

The previous step uses 2 identical docker containers, one per lane, to read Car ID data from suitable sensors. (This is currently using ZoomRoom's hardware). This basic data is sent to an MQTT broker also running in a container on the Pi.
This Step 1 data looks like this:

```{"car": 1, "timestamp": 1713646107871835293, "lane": 2}```

## Step 2 - lapcounter-server-generate-lapdata

This step takes the basic timestamp data and converts it into lap time data which can be consumed by the React from end.
the initial release will stick with ZoomRoom's json format, so I can use my own React JS based front end, which I already have working.

The existing subfolder ```lapcounter-server-lapdata``` creates mocked lapdata provides the correct output format. I need to modify it to grab the initial data from MQTT instead of generating it randomly.

Future versions will publish this data to another MQTT queue so it can be consumed in a variety of formats, and maybe send to a database.





I need to experiment with MQTT compared to a direct WebSocket connection (as used curently), then compared to MQTT-over-WebSockets. The advantage of MQTT, I think, is reliability, with retries being handled automatically, as well as the easy publish/subscribe model which works over a network.
