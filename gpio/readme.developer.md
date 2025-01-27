# Build Instructions

## Create and push a cross platform build.

Use `build-and-push.ps1` from the parent folder

Note that we build 2 versions:

* linux/amd64 for local use (run from WSL2)
* arm/v8 for Raspberry Pi 3A

Sample build command

```
docker buildx build --platform linux/arm/v7,linux/arm64/v8,linux/amd64 --push -t gregkwoods/ lapcounter-server-gpio:latest .
```

## Create a local image which creates mock lapdata

It has no dependencies on GPIO, so can be run on a developer laptop.
There is no need to push it to dockerHub, so we will just use the regular docker build

```
docker build -f ./Dockerfile.Mock -t lapcounter-server-gpio:latest .
```

And to run it locally

```
docker run --env-file ../.env.dev lapcounter-server-gpio
```

## Running Locally Without Docker

For consistency, I;d prefer the Docker workflow is used, but for rapid iterations where a local copy is useful, remember to set local
enviroment variables as per ../.env.dev