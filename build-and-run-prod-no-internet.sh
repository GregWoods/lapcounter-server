# For running on the raspberry pi, without internet. Doesn't attempt to pull latest images
docker compose --file compose.prod.yaml up --pull never --detach