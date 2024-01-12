# subscribe to mqtt topic and print message to console for testing

# About asyncio...
#   why do i need asyncio in this code?
#     it only does one thing, generate driver data at random intervals.
#   The real script may benefit... 
#     if an mqtt pub was blocking, it may hold up the reading of another driver's lap

import asyncio
import json
import random
import time
import sys
import os
import aiomqtt
import paho.mqtt as mqtt

PORT = 8080

numberOfDrivers = 5
baseLapTime = 5
abilityRangeMax = 4.2
lapTimeRangeMax = 3.5
outlierExtraLapTimeMin = 5
outlierExtraLapTime = 13
outlierLowestFrequency = 5 #best driver will average a bad lap every 30 laps


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


async def send_message():
    print("send_message")
    #Create a list of drivers each with their own abilities
    driverRange = [i for i in range(1,numberOfDrivers+1)]
    drivers = list(map(lambda n: Driver(n, time.time()), driverRange))

    async with aiomqtt.Client("localhost") as client:
        while True:
            #Since I'm unure how to have 6 separate timers going, each with their own schedule, 
            #  I'm going to fake it by keeping a running total of system time for each driver
            #  and comparing to current system time

            timenow = time.time()

            for driver in drivers:
                
                #if timenow > driver.nextLapAt and driver.driverNumber != 2:    #driver 2 doesn't post any laps
                if timenow > driver.nextLapAt:
                    driver.dbg()    
                    lapdata = {"type": "lap", "car": driver.driverNumber, "time": driver.nextLapAt}
                    lapjson = json.dumps(lapdata)
                    await client.publish("lap", payload=lapjson)
                    print(lapdata)
                    driver.generateLap()

            await asyncio.sleep(0.001)


async def schedule_tasks():
    # running tasks concurrently
    # We could have each driver have their own task, each task waits its own
    #   calculated random period before firing.
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(
            send_message())
        #task2 = tg.create_task(
        #    everyFiveSeconds())


# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
