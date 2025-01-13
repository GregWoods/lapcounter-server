docker buildx build -f Dockerfile.fastAPI.prod --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-api:$version -t gregkwoods/lapcounter-server-api:latest . --push
