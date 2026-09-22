# Production React image (nginx serving a static bundle).
#
# VITE_* values are inlined by Vite at BUILD time, so they are passed as build
# args here - setting them in a compose file has NO effect on this image.
#
# The API/MQTT addresses are NOT among them any more: the bundle works them out at runtime
# from the host that served the page (react/src/endpoints.js), so this one image runs on
# any Pi at any address. Only the admin PIN is still baked in.
#
# VITE_ADMIN_PIN: if unset, AdminAuthContext treats `pinRequired` as false and
# the Admin pages are open to anyone on the network. Note the PIN is inlined
# into the JS bundle, so it is a speed bump, not security.

$version = git rev-parse --short HEAD

$adminPin = "1234"

docker buildx build -f Dockerfile.prod `
    --platform linux/arm/v7,linux/arm64/v8,linux/amd64 `
    --build-arg VITE_CAR_MEDIA_FOLDER=media/cars `
    --build-arg VITE_ADMIN_PIN=$adminPin `
    -t gregkwoods/lapcounter-server-react:$version `
    -t gregkwoods/lapcounter-server-react:latest `
    . --push
