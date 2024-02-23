$version = "0.1.10"

#docker buildx create --use     
cd ./lapcounter-server-test-mqtt-latency
docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-test-mqtt-latency:$version -t gregkwoods/lapcounter-server-test-mqtt-latency:latest . --push
cd ../lapcounter-server-lapdata
docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-lapdata:$version -t gregkwoods/lapcounter-server-lapdata:latest . --push
#cd ../lapcounter-server-gpio
#docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-gpio . --push
cd ..
