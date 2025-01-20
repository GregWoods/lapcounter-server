#!/bin/bash

# For running on the raspberry pi, without internet. Doesn't attempt to pull latest images
#  It simply re-creates the containers from the images that are already on the system.

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root" >&2
  exit 1
fi

sudo docker compose --file compose.prod.yaml up --pull never --detach
