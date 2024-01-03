
import asyncio

# i want to run everySecond() and everyFiveSeconds() at the same time

# i want to run everySecond() and everyFiveSeconds() at the same time
#put everySecond() and everyFiveSeconds() in a task group

async def everyFiveSeconds():
    while True:
        print("5s task")
        await asyncio.sleep(5)

async def everySecond():
    while True:
        print("every second")
        await asyncio.sleep(1)


async def main():
    # running tasks concurrently
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(
            everySecond())

        task2 = tg.create_task(
            everyFiveSeconds())


asyncio.run(main())
#loop = asyncio.get_event_loop() 
#loop.run_forever(everySecond)