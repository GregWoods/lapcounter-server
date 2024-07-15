docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-api:$version -t gregkwoods/lapcounter-api:latest . --push
