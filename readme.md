# What is Lapcounter-Server

Lapcounter-Server is the software portion of a Scalextric Digital Race Management System.
A combination of hardware and software counts laps on a Scalextric Digital slot racing circuit.
It includes a real time leaderboard viewable in a web browser.

For more technical details, please see **readme.developer.md**

## Hardware
The hardware is a Raspberry Pi 3A connected to a 2 lane car id sensor circuit created by [ZoomRoom](https://www.slotforum.com/members/zoomroom.24952/) 

## Software
the original project, well documented on [slotforum](https://www.slotforum.com/threads/wifi-raspberry-pi-based-lap-counter-timer.197059/), was a great accomplishment during a few months of lockdown. I did dislike the UI (I have a pet hate for 7 segment LED fonts!), so I developed my own ReactJs based front end. Once that was in a decent state, I started to look at reworking the backend so I could add features not possible with all the logic in the front end code. 

![My reworked React JS UI](docs/shakedown.gif)

## Features

* Nice fonts, and nice colours which map to the powerbase/hand throttle colours (hackable)
* Start lights beep the countdown. Not realistic, but nice!
* Drivers only appear on the leaderboards when they first cross the line, so the screen looks uncluttered if only 2 drivers are racing
* Once the winning driver crosses the line, each driver finishes their lap, then the race is over
    * This can give some odd looking ordering of events, as seen in the GIF, where the ordering is P1, P6, P3, P4, P2, P5.
    * The logic is correct, as is based on a greater number of laps completed beats less laps completed, then lower total race time beats higher total race time for drivers on the same lap
* There are just a few predefined race types, because I got tired of drivers debating whether to run a 20 or 25 lap race. Each race type is kept substantially different from the others, with choices intentionally limited (but can be hacked)
* Yellow flag can be triggered by hitting the space bar
* Crossing the finish line under yellow flag results in lap being discarded
* Driver with fastest lap of the race has their fastest lap time shown in purple
* Driver names quickly editable (not shown)
* [Coming Soon] A nice UI for uploading and using car images

## Notes from the GIF

* The UI to modify the car images is not finished. The old FSR logo from the Zoomroom original code has been left in for now
* Note that the GIF was generated from fake data, so it takes longer than in most real races for all 6 cars to cross the line and appear on the board


# End User Setup- Running on a Raspberry Pi

## Install the OS
We do not need a GUI, so I'm not using Raspberry Pi OS.
Instead I am using Ubuntu 32bit LTS (currently 22.10)
Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to set up your SD card

* Other general purpose OS -> Ubuntu -> Ubuntu Server 24.04 LTS (64 bit)
* Apply OS customisation settings: EDIT SETTINGS    
    * Hostname: lapcounter-server
    * Set username and password: <choose your own, keep a record>
    * Configure wireless LAN: <use your WiFi details>
    * Save
* Would you like to apply OS customisation settings: YES
* Erase card, are you sure: YES


## Install Docker
```
# remove old packages, not needed in Ubuntu 24.04
# for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove $pkg; done

# download and run the superb convenience script
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# test docker
docker run busybox echo "hello from busybox"

# The docker service should already be set to run from boot
```

## Bootstrap the app
```
cd ~
wget https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/systemd/lapcounter.service
wget https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.yaml
cp lapcounter.service /etc/systemd/system/lapcounter.service
sudo systemctl enable lapcounter.service
sudo systemctl start lapcounter.service
```