$version = git rev-parse --short HEAD
docker buildx build -f ./Dockerfile --platform linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-ble:$version -t gregkwoods/lapcounter-server-ble:latest . --push
