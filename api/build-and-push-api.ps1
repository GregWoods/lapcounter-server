$version = git rev-parse --short HEAD
# --build-context database: the image carries database/migrations/ for the migrate
# service (#84), which lives outside this folder's build context.
docker buildx build -f Dockerfile.prod --build-context database=../database --platform linux/arm/v7,linux/arm64/v8,linux/amd64 -t gregkwoods/lapcounter-server-api:$version -t gregkwoods/lapcounter-server-api:latest . --push
