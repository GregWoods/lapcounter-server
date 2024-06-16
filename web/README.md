# Standalone Scalextric Digital Lap Counter

## Quick Start (Developer)

* see docker compose file and related docs for starting the back end
* nvm use 20.12.2
* npm install
* npm start
* Use the browser developer tools to fix the windows size to 1920x1080 (it can be scaled down via zoom)

## Quick Start (Production)

This is to be run inside a a docker container running the nginx web server.
See: https://hub.docker.com/_/nginx
```
npm run build
docker build -t gregkwoods/lapcounter-web:0.0.1 .

```
