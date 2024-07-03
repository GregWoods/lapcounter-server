for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove $pkg; done
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
rm get-docker.sh
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/compose.prod.yaml
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/.env.prod
mkdir -p ./mosquitto/config
curl -o ./mosquitto/config/mosquitto.conf  https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/mosquitto/config/mosquitto.conf

#sudo docker compose --file compose.prod.yaml up --detach
