# Hardware

A single Raspberry Pi (recommended model is 3A+ or Pi Zero 2 W) runs the software stack, but all user interface is viewed in a web browser on a seaprate device such as a laptop.

In order for the system to be portable to village halls and other locations without internet access, a portal wireless access point is used. I use a small, cheap and simple 2.4GHz WiFi USB-powered access point. It providers DHCP services for the Raspberry Pi and Laptop being used as the display. In the future other devices will be able to connect. Although internet access is required to set up the software on the Raspberry Pi, it is not needed after this initial setup. If your system is never going to be portal, the Raspberry Pi and laptop/mini-PC can simply connect to your home network.

# Software Architecture

## Rationale

### Layered approach using Docker

Developing and bug fixing the GPIO-reading part of the code is a pain. It has to be done directly on the Raspberry Pi which has access to the GPIO pins and hardware car ID sensors. (VS Code's remote SSH is too slow). We want to keep this part of the development as short and simple as possible. To enable this, I've chosen to not use any hand-written threading code, or even asyncio (though the MQTT library, and GPIO libraries do use threading internally). The theory is that Docker and the OS are good at handling multi-threading, so I'll trust that they do their job. I intend doing some more rigorous hardware testing later. If this reveals it can't handle 2 cars crossing the line at the same time, then I'll revisit it. I therefore do not worry about one MQTT publish interfering with the other lane's GPIO read. 

### Isn't this going to be slow?

Initial tests indicate not. Using a high level, interpreted language, on top of Docker containers to run the code and another Docker container to run the data queue. Then transferring that data over http, will all no doubt makes any microcontroller developers in the slot car space a bit queasy! But it is a tried and tested tech stack, and once setup it is quick to develop, easy to modify, and is running on a multi-core gigahertz-plus CPU. If testing shows it is laggy, or misses laps, then I will revisit my assumptions... but not before. 

## The Layers

1. Layer 1 is a Python script (running in Docker) which **reads GPIO Car ID data from a single lane hardware sensor, then publishes this to the "car_timestamp" MQTT queue**. This can only run on a physical Raspberry Pi with the lane sensors attached. So to make local development easier, Layer 1 can be replaced with a Python script (or Docker container) which creates random Car ID data, and publishes it to the same "car_timestamp" MQTT queue. 

2. Layer 2 is a running Python script (running in Docker) which **subscribes to the "car_timestamp" queue, and calculates the lap time for that car, then publishes to the "lap" MQTT queue** This script uses an in-memory record of each car's previous timestamp. The output format is the same as ZoomRoom's (a slotforunm user) Python original script. This data format will work with my current React app (with a small alteration to use MQTT instead of websockets). Eventually, layer 2 will use persistent storage and add addional features.

3. Layer 3 is the Web App. The original ZoomRoom web app has been re-written from the ground up in React. It is a vast improvement in look and feel, but has reached the limit of what I can do with it. To add additional features, I need to move Driver, Car, Race and Lap data out of the front end javascript and into the back end where they can be properly stored. Currently, only one browser can attach to the lapcounter, and I want multiple devices to be able to connect, all showing up to date info.

4. Linking the 3 layers together are  message queues. I am using a mosquitto server to host these queues. Mosquitto runs in it's own docker container. It is an easy to use and designed to be resilient. The publish-subscribe model makes for rapid development of very well isolated layers. For example it is trivial to swap out the real car ID reading Layer 1 for the Fake Data version. 


# The Future

In the future, other layers and Docker containers will be added for things like database storage and reporting.

I envisage the react web app being able to serve different types of pages, from a TV sized lap counter, to individual driver progress on a phone screen. 
The API which serves these could also provide data to hardware start grid lights, and trackside race status LEDs (yellow flag etc)
