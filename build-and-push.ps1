# Note: For internal use only. No other developer can push to my Docker Hub account. 

# Note: Use Ubuntu not Powershell
## Why???

#cd /mnt/c/Users/gregw/projects/lapcounter-server/

docker login -u gregkwoods
#  supplying password/personal access token in CLI isn't allowed anymore. Interactive login is required

docker buildx create --use

#cd ./lapcounter-server-test-mqtt-latency
#docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-test-mqtt-latency:$version -t gregkwoods/lapcounter-server-test-mqtt-latency:latest . --push

cd gpio
./build-and-push-gpio.ps1
cd ..

cd lapdata
./build-and-push-lapdata.ps1
cd ..

cd react
./build-and-push-react.ps1
cd ..

cd api
./build-and-push-api.ps1
cd ..
