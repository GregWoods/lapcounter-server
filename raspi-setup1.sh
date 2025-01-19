#!/bin/bash

# Bootstrap instructions
#
# curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/raspi-setup1.sh
# chmod 755 raspi-setup1.sh && sudo ./raspi-setup1.sh

echo "Lapcounter-Server Setup"
# Ensure the script is run as root
if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root" >&2
  exit 1
fi

echo "Get all bootstrap files"
curl -fsSL https://get.docker.com -o get-docker.sh
mkdir -p ./mosquitto/config
curl -o ./mosquitto/config/mosquitto.conf  https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/mosquitto/config/mosquitto.conf

echo "Remove any existing Docker components"
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove $pkg; done

echo "Install Docker"
sudo sh get-docker.sh && rm get-docker.sh

echo "Docker installed. Downloading and running raspi-setup2.sh"
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/raspi-setup2.sh
chmod 755 raspi-setup2.sh
source ./raspi-setup2.sh