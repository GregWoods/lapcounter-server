# Standalone Scalextric Digital Lap Counter - React Web Application

## Create and push a cross platform build.

```build-and-push-react.ps1```

The commands in this script can be run individually and modified, if for example, during development you didn't want to push an interim
build to DockerHub, replace `--push` with `--load`.

Note that we build for 3 architectures:

* `linux/amd64`for local use (run from WSL2 or Docker) using the mocked gpio 
* `linux/arm/v7` for 32 bit Raspberry Pi OS running on the Pi Zero 2 W or Pi 3A+
* `linux/arm64/v8` for 64 bit Raspberry Pi OS running on a 1Gb+ Pi 3 or later


## Run it locally in Docker

Correctly set up environment variables are needed for any of these containers to run. So instead of using `docker run` directly, we run can run the container using docker compose.

```docker compose -f ../compose.dev.yaml up --build react```
