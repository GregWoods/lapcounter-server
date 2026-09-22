# dbwriter had no push script, so it was absent from the Pi compose files -
# meaning those deployments ran with NO lap persistence at all.
#
# Building here rather than on the Pi matters: psycopg2-binary publishes no
# armv7l wheel, so the 32-bit Pi compiles it from source (~7 minutes, dominated
# by installing a ~200MB toolchain onto a slow SD card).

$version = git rev-parse --short HEAD

docker buildx build `
    --platform linux/arm/v7,linux/arm64/v8,linux/amd64 `
    -t gregkwoods/lapcounter-server-dbwriter:$version `
    -t gregkwoods/lapcounter-server-dbwriter:latest `
    . --push
