$version = git rev-parse --short HEAD
docker buildx build -f ./Dockerfile        --platform linux/arm/v7,linux/arm64/v8   -t gregkwoods/lapcounter-server-gpio:$version        -t gregkwoods/lapcounter-server-gpio:latest . --push
docker buildx build -f ./Dockerfile.Mocked --platform linux/arm/v7,linux/amd64      -t gregkwoods/lapcounter-server-mocked-gpio:$version -t gregkwoods/lapcounter-server-mocked-gpio:latest . --push
#arm/v8 fails install gcc for reasons unknown. Not vital. Mocked will most likely be used on dev laptop