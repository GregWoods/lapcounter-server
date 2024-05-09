# Build Instructions

## Create and push a cross platform build.

* linux/amd64 for local use (run from WSL2)
* arm/v7 for Raspberry Pi 3A

```
docker buildx build --platform linux/amd64,linux/arm/v7 --push -t gregkwoods/lapcounter-server-gpio:latest .
```

## Create a local image which creates mock lapdata

It has no dependencies on GPIO, so can be run on a developer laptop.
There is no need to push it to dockerHub, so we will just use the regular docker build

```
docker build -f ./Dockerfile.Mock -t lapcounter-server-gpio:latest .
```

And to run it locally

```
docker run --env-file ../.env.local lapcounter-server-gpio
```