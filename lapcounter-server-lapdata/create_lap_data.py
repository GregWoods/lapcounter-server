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
    #Create a list of drivers each with their own abilities
    driverRange = [i for i in range(1,numberOfDrivers+1)]
    drivers = list(map(lambda n: Driver(n, time.time()), driverRange))
    
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
                lapjson = json.dumps(lapdata) 
                print(lapjson)

                #await client.publish("lap", payload=lapjson)
                print(lapdata)

                driver.generateLap()
        
        asyncio.sleep(0.001)



async def schedule_tasks():
    # running tasks concurrently
    # We could have each driver have their own task, each task waits its own
    #   calculated random period before firing.
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(
            send_message())
        #task2 = tg.create_task(
        #    everyFiveSeconds())


asyncio.run(schedule_tasks())


#start_server = websockets.serve(send_message, "localhost", PORT)
#asyncio.get_event_loop().run_until_complete(start_server)

#asyncio.get_event_loop().run_until_complete(send_message)
#asyncio.get_event_loop().run_forever()

# windows only - Change to the "Selector" event loop
#asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

asyncio.run(send_message())

"""
# async io mqtt sample

aiomqtt.Client(
    hostname="test.mosquitto.org",  # The only non-optional parameter
    port=1883,
    username=None,
    password=None,
    logger=None,
    client_id=None,
    tls_context=None,
    tls_params=None,
    proxy=None,
    protocol=None,
    will=None,
    clean_session=None,
    transport="tcp",
    keepalive=60,
    bind_address="",
    bind_port=0,
    clean_start=mqtt.client.MQTT_CLEAN_START_FIRST_ONLY,
    properties=None,
    message_retry_set=20,
    socket_options=(),
    max_concurrent_outgoing_calls=None,
    websocket_path=None,
    websocket_headers=None,
)


async def publish_humidity(client):
    await client.publish("humidity/outside", payload=0.38)


async def publish_temperature(client):
    await client.publish("temperature/outside", payload=28.3)


async def main():
    async with aiomqtt.Client("test.mosquitto.org") as client:
        await publish_humidity(client)
        await publish_temperature(client)


# windows only - Change to the "Selector" event loop
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Run your async application as usual
asyncio.run(main())

"""