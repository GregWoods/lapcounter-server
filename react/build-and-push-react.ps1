$version = git rev-parse --short HEAD
docker buildx build -f Dockerfile.prod --platform linux/arm/v7,linux/arm64/v8,linux/amd64 -t gregkwoods/lapcounter-server-react:$version -t gregkwoods/lapcounter-server-react:latest . --push
