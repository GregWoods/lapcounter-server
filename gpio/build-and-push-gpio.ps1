$version = git rev-parse --short HEAD
docker buildx build -f ./Dockerfile        --platform linux/arm/v7,linux/arm64/v8   -t gregkwoods/lapcounter-server-gpio:$version        -t gregkwoods/lapcounter-server-gpio:latest . --push
# No mocked-gpio image any more: dev builds this Dockerfile and runs the mocks from a
# bind mount (compose.dev.yaml, #101).