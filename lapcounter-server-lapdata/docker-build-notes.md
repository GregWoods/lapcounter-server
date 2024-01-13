To build images for Raspberry Pi, first create a builder

```
docker buildx create --name raspi3 --platform linux/arm/v7
```

Then, to build for both my local developer laptop (Windows, but Docker in Linux mode), and for Raspberry Pi 3...

```
docker buildx use raspi3

docker buildx build --platform linux/amd64,linux/arm/v7 -t gregkwoods/lapcounter-server-lapdata:0.0.1 . --push
```