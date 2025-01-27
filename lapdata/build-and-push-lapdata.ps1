$version = git rev-parse --short HEAD
docker buildx build --platform linux/amd64,linux/arm64/v8 -t gregkwoods/lapcounter-server-lapdata:$version -t gregkwoods/lapcounter-server-lapdata:latest . --push
