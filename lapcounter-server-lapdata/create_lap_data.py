import asyncio
import json
import random
import time
import sys
import os
import aiomqtt
import paho.mqtt as mqtt

PORT = 8080

numberOfDrivers = 6
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




async def send_message(driver):
    async with aiomqtt.Client("localhost") as client:
        while True:
            driver.generateLap()
            await asyncio.sleep(max(0, driver.nextLapAt - time.time()))            
            driver.dbg()    
            lapdata = {"type": "lap", "car": driver.driverNumber, "time": driver.nextLapAt}
            lapjson = json.dumps(lapdata)
            await client.publish("lap", payload=lapjson)
            print(lapdata)


# Create a list of drivers each with their own abilities
driverRange = [i for i in range(1,numberOfDrivers+1)]
drivers = list(map(lambda n: Driver(n, time.time()), driverRange))


# Create a task for each driver
async def schedule_tasks():
    async with asyncio.TaskGroup() as tg:
        for driver in drivers:
            tg.create_task(send_message(driver))       


# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
