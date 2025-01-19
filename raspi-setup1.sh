#!/bin/bash

echo "Lapcounter-Server Setup"
echo "IMPORTANT: Run under 'sudo'"

echo "Get all bootstrap files"
curl -fsSL https://get.docker.com -o get-docker.sh
mkdir -p ./mosquitto/config
curl -o ./mosquitto/config/mosquitto.conf  https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/mosquitto/config/mosquitto.conf

echo "Remove any existing Docker components"
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove $pkg; done

echo "Install Docker"
sudo sh get-docker.sh && rm get-docker.sh

echo "Docker installed. Now running raspi-setup2.sh"
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/raspi-setup2.sh
chmod 755 raspi-setup2.sh
source ./raspi-setup2.sh