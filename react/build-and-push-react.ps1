$version = git rev-parse --short HEAD
docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64/v8 -t gregkwoods/lapcounter-server-react:$version -t gregkwoods/lapcounter-server-react:latest . --push
