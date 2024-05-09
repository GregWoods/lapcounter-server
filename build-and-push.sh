# Note: For internal use only. No other developer can push to my Docker Hub account. 

$version = "0.0.6"

#docker login -u gregkwoods -p $env:DOCKER_PASSWORD_FROM_KEEPER
#docker buildx create --use

#cd ./lapcounter-server-test-mqtt-latency
#docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-test-mqtt-latency:$version -t gregkwoods/lapcounter-server-test-mqtt-latency:latest . --push

cd lapcounter-server-gpio
docker buildx build --platform linux/arm/v7 -t gregkwoods/lapcounter-server-gpio:$version -t gregkwoods/lapcounter-server-gpio:latest . --push
docker buildx build -f ./Dockerfile.Mock --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-mocked-gpio:$version -t gregkwoods/lapcounter-server-mocked-gpio:latest . --push
cd ..

cd lapcounter-server-lapdata
docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-lapdata:$version -t gregkwoods/lapcounter-server-lapdata:latest . --push
cd ..