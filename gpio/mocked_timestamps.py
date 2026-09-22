# This script generates mock lap times for ALL lanes and all drivers and sends them to the MQTT broker.
#   whereas gpio_to_timestamps.py generates data for only ONE lane (but we run one docker container per lane)


import asyncio
import json
import random
import time
import sys
import os
import aiomqtt

from layer1_clock import CLOCK, HEARTBEAT_INTERVAL_S, MQTT_CLOCK_TOPIC, counter_ms


mqtt_hostname = os.getenv('MQTT_HOSTNAME')
numberOfDrivers = int(os.getenv('MOCK_NUMBER_OF_DRIVERS'))

print(f"MQTT_HOSTNAME: {mqtt_hostname}")
print(f"MOCK_NUMBER_OF_DRIVERS: {numberOfDrivers}")

publish_topic = "car_timestamp"
print(f"Publishing to topic: {publish_topic}")

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
        self.nextLapAt = currentTime
        self.nextLapTime = 0
        self.generateLap()

    def generateLap(self):
        self.nextLapTime = self.baseLapTime + random.uniform(0, self.lapTimeRange)
        if random.uniform(0, outlierLowestFrequency) <= 0:
            self.nextLapTime = self.nextLapTime + random.uniform(outlierExtraLapTimeMin, outlierExtraLapTime)
        self.nextLapAt = self.nextLapAt + self.nextLapTime
        return self

    def dbg(self):
        print("---------------")
        print("Driver", self.driverNumber)
        print("Lap Time: ", self.nextLapAt)
        print("Next Lap At: ", self.nextLapAt)


async def send_lap_time(driver):
    async with aiomqtt.Client(mqtt_hostname) as client:
        while True:
            driver.generateLap()
            await asyncio.sleep(max(0, driver.nextLapAt - time.time()))
            # Stamped at "detection", as the real GPIO callback does — not after the
            # publish. See gpio/layer1_clock.py.
            crossing_counter_ms = counter_ms()
            lane_idx = random.randint(1, 2)
            lapdata = {"car": driver.driverNumber, "lane": lane_idx,
                       "counter_ms": crossing_counter_ms, "clock": CLOCK}
            lapjson = json.dumps(lapdata)
            print(lapjson)
            await client.publish(publish_topic, payload=lapjson)


async def send_clock_heartbeat():
    """A bare counter reading once a second, for lapdata to anchor against. Lap 1 is
    timed from lights-out, before any car has crossed, so crossings alone would leave it
    with nothing to anchor against at exactly the moment it needs one."""
    async with aiomqtt.Client(mqtt_hostname) as client:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            await client.publish(MQTT_CLOCK_TOPIC, payload=json.dumps(
                {"clock": CLOCK, "counter_ms": counter_ms()}))

# Create a list of drivers each with their own abilities
driverRange = [i for i in range(1,numberOfDrivers+1)]
drivers = list(map(lambda n: Driver(n, time.time()), driverRange))


# Create a task for each driver
async def schedule_tasks():
    async with asyncio.TaskGroup() as tg:
        for driver in drivers:
            tg.create_task(send_lap_time(driver))
        tg.create_task(send_clock_heartbeat())


# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
