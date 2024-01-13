import asyncio
import time
import sys
import os
import aiomqtt
import paho.mqtt as mqtt


async def subscribe():
    async with aiomqtt.Client("localhost") as client:
        async with client.messages() as messages:
            await client.subscribe("lap")
            async for message in messages:
                print(message.payload)


async def schedule_tasks():
    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscribe())


# Change to the "Selector" event loop if platform is Windows
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

asyncio.run(schedule_tasks())
