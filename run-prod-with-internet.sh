#!/bin/bash

# For running on the raspberry pi, with internet, so the latest images are pulled

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root" >&2
  exit 1
fi

echo "Download and Run the lapcounter-server containers"
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.prod.yaml
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/.env.prod

sudo docker compose --file compose.prod.yaml --pull-policy pull --policy always
sudo docker compose --file compose.prod.yaml up --detach

