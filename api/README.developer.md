# Standalone Scalextric Digital Lap Counter - Python API

For local development I am favouring using Docker.
Sometimes though, things are just easier running localy. In those hopefully rare occasions...

## Use pyenv!

It is installed globalled, and allows changing python version
 ```
pyenv versions
pyenv install --list
pyenv install 3.12.2
 ```

## Running with Docker

From the ```api``` folder, we need to specify the compose file in the parent folder
```
docker compose -f ../compose.dev.yaml up --build --detach api
```


### Endpoints (see app/main/main.py)

Auto generated API documentation.
```
http://127.0.0.1:8000/docs
```
