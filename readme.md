# What is Lapcounter-Server

Lapcounter-Server is the software portion of a Scalextric Digital Race Management System.
It is a combination of hardware and software to count laps on a Scalextric Digital slot racing circuit.
It includes a real time leaderboard viewable in a web browser.

## Hardware
The hardware is a Raspberry Pi 3A connected to a 2 lane car id sensor circuit created by *ZoomRoom*. 

## Software
the original project, well documented on [slotforum], was a great accomplishment during a few months of lockdown. However, felt the UI was lacking, so developed my own ReactJs based front end. Once that was in a decent state, I started to look at reworking the backend so I could add features not possible with all the logic in the front end code. 

For more technical details, please see **readme.developer.md**


# End User Setup- Running on a Raspberry Pi

## Install the OS
We do not need a GUI, so I'm not using Raspian.
Instead I am using Ubuntu 32bit LTS (currently 22.10)
Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to set up your SD card


## Install Docker
```
# remove old packages, just in case
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove $pkg; done

# download and run the superb convenience script
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# test docker
docker run busybox echo "hello from busybox"

# The docker service should already be set to run from boot
```

## Bootstrap the app
```
mkdir ~/lapcounter-server
cd ~/lapcounter-server
wget github https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/systemd/lapcounter.service
wget github https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.yaml
cp lapcounter.service /etc/systemd/system/lapcounter.service
sudo systemctl enable lapcounter.service
sudo systemctl start lapcounter.service
```