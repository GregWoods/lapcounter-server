
# End User Setup- Running on a Raspberry Pi
[see my more recent notes in Docker]

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
#the following looks wrong... it doesn't fully use docker. Merge in my OneNote
cd ~
wget https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/systemd/lapcounter.service
wget https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.yaml
cp lapcounter.service /etc/systemd/system/lapcounter.service
sudo systemctl enable lapcounter.service
sudo systemctl start lapcounter.service
```
