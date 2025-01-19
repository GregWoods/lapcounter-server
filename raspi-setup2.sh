#!/bin/bash

echo "Download and Run the lapcounter-server containers"
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.prod.yaml
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/.env.prod
sudo docker compose --file compose.prod.yaml up --detach
 