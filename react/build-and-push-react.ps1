$version = git rev-parse --short HEAD
docker buildx build -f Dockerfile.prod --platform linux/amd64,linux/arm64/v8 -t gregkwoods/lapcounter-server-react:$version -t gregkwoods/lapcounter-server-react:latest . --push
