# Note: For internal use only. No other developer can push to my Docker Hub account. 

# Note: Use Ubuntu not Powershell

#cd /mnt/c/Users/gregw/projects/lapcounter-server/

$version = "0.0.9"

#docker login -u gregkwoods -p $env:DOCKER_PASSWORD_FROM_KEEPER
#  supplying password in CLI isn't allowed anymore
#docker buildx create --use

#cd ./lapcounter-server-test-mqtt-latency
#docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-test-mqtt-latency:$version -t gregkwoods/lapcounter-server-test-mqtt-latency:latest . --push

cd gpio
docker buildx build --platform linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-gpio:$version -t gregkwoods/lapcounter-server-gpio:latest . --push
docker buildx build -f ./Dockerfile.Mock --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-mocked-gpio:$version -t gregkwoods/lapcounter-server-mocked-gpio:latest . --push
cd ..

cd lapdata
docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-lapdata:$version -t gregkwoods/lapcounter-server-lapdata:latest . --push
cd ..

cd react
docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-react:$version -t gregkwoods/lapcounter-server-react:latest . --push
cd ..

#cd web
#docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-web:$version -t gregkwoods/lapcounter-web:latest . --push
#cd ..
