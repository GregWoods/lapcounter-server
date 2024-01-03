import asyncio
import json
import random
import time
import paho.mqtt.client as mqtt

PORT = 8080
mqtt_host = "172.18.0.3"    # try "mosquitto"

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
    print("Server started")
    
    #Create a list of drivers each with their own abilities
    driverRange = [i for i in range(1,numberOfDrivers+1)]
    drivers = list(map(lambda n: Driver(n, time.time()), driverRange))


    print("stuff")
    while True:
        timenow = time.time()

        for driver in drivers:
            
            #if timenow > driver.nextLapAt and driver.driverNumber != 2:    #driver 2 doesn't post any laps
            if timenow > driver.nextLapAt:
                driver.dbg()
                lapdata = {"type": "lap", "car": driver.driverNumber, "time": timenow}  #driver.nextLapAt}
                sendlap = json.dumps(lapdata) 
                
                print(sendlap)
                client.publish("send_lap", payload=sendlap, qos=0, retain=False)

                driver.generateLap()

        await asyncio.sleep(0.001)


def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))


print(f"MQTT Host: {mqtt_host}")


client = mqtt.Client()
client.on_connect = on_connect
client.connect(mqtt_host)

# create async loop which runs every 0.001 seconds
loop = asyncio.get_event_loop()
loop.run_until_complete(send_message())
loop.run_forever()



