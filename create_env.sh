#!/bin/bash

# Add environment variables to ~/.bashrc
echo 'export MQTT_HOSTNAME=127.0.0.1' >> ~/.bashrc
echo 'export MINIMUM_LAP_TIME=3.0' >> ~/.bashrc

# Load the updated ~/.bashrc again to apply the changes
source ~/.bashrc