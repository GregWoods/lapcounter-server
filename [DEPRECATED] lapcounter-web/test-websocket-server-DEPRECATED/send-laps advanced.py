import asyncio
import json
import websockets
import random
import time


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



async def send_message(ws, path):
    print("Server started")
    
    #Create a list of drivers each with their own abilities
    driverRange = [i for i in range(1,numberOfDrivers+1)]
    drivers = list(map(lambda n: Driver(n, time.time()), driverRange))

    #generate next laps for all drivers
    #drivers = list(map(lambda d: d.generateLap(), drivers))
    print("stuff")
    while True:
        #Since I'm unure how to have 6 separate timers going, each with their own schedule, 
        #  I'm going to fake it by keeping a running total of system time for each driver
        #  and comparing to current system time

        timenow = time.time()

        #Loop through all drivers
        for driver in drivers:
            
            #if timenow > driver.nextLapAt and driver.driverNumber != 2:    #driver 2 doesn't post any laps
            if timenow > driver.nextLapAt:
                driver.dbg()
                lapdata = {"type": "lap", "car": driver.driverNumber, "time": driver.nextLapAt}
                sendlap = json.dumps(lapdata) 
                print(sendlap)
                await ws.send(sendlap)
                driver.generateLap()

        await asyncio.sleep(0.001)

start_server = websockets.serve(send_message, "localhost", PORT)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
