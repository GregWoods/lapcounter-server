# Dev-only: the simulated track behind the mocked-gpio lane containers. It owns every
# car's lap timing and which lane each car is in, and sends each crossing to that lane's
# fake sensor board (mock_rpi_gpio.py) on `mock/gpio/lane<N>`. It publishes no
# car_timestamp itself: the lane containers, running the real gpio_to_timestamps.py, do.
#
# Lap timing has to live in this one process: two independent mocks couldn't know when a
# car crossed on the other lane.
#
# Env: MQTT_HOSTNAME, MOCK_NUMBER_OF_DRIVERS (1-6), MOCK_LANE_CHANGE_PROBABILITY (per lap,
# default 0.15).

import json
import logging
import os
import random
import time

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('mock_track')

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
numberOfDrivers = int(os.getenv('MOCK_NUMBER_OF_DRIVERS'))
laneChangeProbability = float(os.getenv('MOCK_LANE_CHANGE_PROBABILITY') or 0.15)

logger.info(f"MQTT_HOSTNAME: {mqtt_hostname}")
logger.info(f"MOCK_NUMBER_OF_DRIVERS: {numberOfDrivers}")

LANES = 2
# What mock_rpi_gpio.py listens on (not imported: it needs a LANE_NUMBER at import).
MOCK_GPIO_TOPIC = 'mock/gpio/lane{}'

baseLapTime = 5
abilityRangeMax = 4.2
lapTimeRangeMax = 3.5
outlierExtraLapTimeMin = 5
outlierExtraLapTime = 13
outlierLowestFrequency = 5


class Driver:
    def __init__(self, drvNum, currentTime):
        self.driverNumber = drvNum
        self.baseLapTime = baseLapTime + random.uniform(0, abilityRangeMax)
        self.lapTimeRange = random.uniform(0, lapTimeRangeMax)
        self.outlierFrequency = random.uniform(0, outlierLowestFrequency)
        self.lane = random.randint(1, LANES)
        self.nextLapAt = currentTime
        self.nextLapTime = 0
        self.generateLap()

    def generateLap(self):
        self.nextLapTime = self.baseLapTime + random.uniform(0, self.lapTimeRange)
        if random.uniform(0, outlierLowestFrequency) <= 0:
            self.nextLapTime = self.nextLapTime + random.uniform(outlierExtraLapTimeMin, outlierExtraLapTime)
        self.nextLapAt = self.nextLapAt + self.nextLapTime
        # Mostly staying in one lane, with an occasional change, so a car's laps are
        # stamped by one lane container and then the other now and then.
        if random.random() < laneChangeProbability:
            self.lane = LANES + 1 - self.lane
        return self


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(mqtt_hostname)
client.loop_start()

drivers = [Driver(n, time.time()) for n in range(1, numberOfDrivers + 1)]

while True:
    driver = min(drivers, key=lambda d: d.nextLapAt)
    time.sleep(max(0, driver.nextLapAt - time.time()))
    # Sent to whichever lane the car is in for this crossing. If that lane's container is
    # down, nobody hears it: the crossing is lost, as it would be on the Pi.
    client.publish(MOCK_GPIO_TOPIC.format(driver.lane), json.dumps({'car': driver.driverNumber}))
    logger.info(f"car {driver.driverNumber} crossed lane {driver.lane}")
    driver.generateLap()
