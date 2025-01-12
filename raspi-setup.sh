#!/bin/bash
echo "Lapcounter-Server Setup"

echo "Get all bootstrap files"
curl -fsSL https://get.docker.com -o get-docker.sh
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.prod.yaml
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/.env.prod
mkdir -p ./mosquitto/config
curl -o ./mosquitto/config/mosquitto.conf  https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/mosquitto/config/mosquitto.conf

echo "Remove any existing Docker components"
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove $pkg; done

echo "Install Docker"
sudo sh get-docker.sh && rm get-docker.sh

echo "Run the lapcounter-server container"
sudo docker compose --file compose.prod.yaml up --detach
