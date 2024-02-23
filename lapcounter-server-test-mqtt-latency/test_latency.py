import asyncio
import time
import sys
import os
import aiomqtt
import paho.mqtt as mqtt
import json
import time
import os
from dotenv import load_dotenv


# Load dev environment variables. We don't override existing variables set using docker compose --env-file
#   which is used in production
#load_dotenv('../.env.local', override=False)        #only needed if we are running the script outside of the container
mqtt_hostname = os.getenv('MQTT_HOSTNAME')
print(mqtt_hostname)

async def subscribe():
    # replace "localhost" with an environment variable

    async with aiomqtt.Client(mqtt_hostname) as client:
        async with client.messages() as messages:
            await client.subscribe("lap")
            async for message in messages:
                #print(message.payload)
                data = json.loads(message.payload)
                timestamp = data["time"]
                #print(timestamp)
                now = time.time()
                #print(now)
                latency = now - timestamp
                print(latency)


async def schedule_tasks():
    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscribe())




# Change to the "Selector" event loop if platform is Windows
# This is a workaround for a bug in Python 3.8
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
