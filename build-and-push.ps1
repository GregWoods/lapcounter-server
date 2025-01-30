# Note: For internal use only. No other developer can push to my Docker Hub account. 

docker login -u gregkwoods
#  supplying password/personal access token in CLI isn't allowed anymore. Interactive login is required

docker buildx create --use

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
