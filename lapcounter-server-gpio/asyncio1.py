import asyncio

async def main():
    print("start main()")
    await asyncio.sleep(2)
    print("end main()")

asyncio.run(main())