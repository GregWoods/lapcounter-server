# Developer Workflow - Layer 1: GPIO and layer 2: Lap Data

## DEPRECATED Document

These instructions are DEPRECATED. I now generally recommend docker for local development.
This should still be useful if Docker proves to be too much of a pain.


## Overview


This page is all about the developer workflow whilst working on the first 2 layers of the architecture

Although I'm using a Windows machine, all scripts are written for Ubuntu on WSL2. This provides greater compatibilty should others want to develop the code, and helps ensure the code will seamlesssly transition to Docker containers.

Note that once Layers 1 and 2 are working, it is easier to run them as Docker containers in the background whilst local development continues in the React app.

## Pre-Requisites

* Pyenv to allow switching of Python versions
*   https://realpython.com/intro-to-pyenv/

```
sudo apt-get install -y make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev \
libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python-openssl

curl https://pyenv.run | bash

# follow the instructions at the end to add pyenv to your path

pyenv install --list
# We want 3.11.0 to match the Docker image we use

pyenv install 3.11.0
pyenv version
```

## Run Layer 1: mocked_timestamp

In an Ubuntu shell

```bash
cd /mnt/c/Users/gregw/projects/lapcounter-server/
source ./setenv.sh
export MQTT_HOSTNAME=localhost
# optional: printenv
cd lapcounter-server-gpio/
source ./.venv/Scripts/activate
# Run the following once
    pip install -r requirements.mocked.txt
    # Expect errors regarding the GPIO module, which is not available on Windows. This is Ok
pyenv shell 3.11.0
python3 --version
#sudo -E python3 mocked_timestamps.py
python3 mocked_timestamps.py
```

## Run Layer 2: timestamp_to_lapdata

In a second Ubuntu shell

```bash
cd /mnt/c/Users/gregw/projects/lapcounter-server/
source ./setenv.sh
export MQTT_HOSTNAME=localhost
cd lapcounter-server-lapdata/
source ./.venv/Scripts/activate
# Run the following once
    pip install -r requirements.mocked.txt
pyenv shell 3.11.0
python3 --version
#sudo -E python3 timestamp_to_lapdata.py
python3 timestamp_to_lapdata.py
```
