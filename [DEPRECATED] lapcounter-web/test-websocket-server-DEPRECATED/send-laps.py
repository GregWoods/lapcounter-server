import asyncio
from datetime import datetime
import json
import websockets

PORT = 8080

async def send_message(ws, path):
    print("Server started")
    carnumber = 1
    while True:
        thistime = datetime.now()
        lapdata = {"type": "lap", "car": carnumber, "time": thistime.timestamp()}
        sendlap = json.dumps(lapdata) 
        print(sendlap)
        await ws.send(sendlap)
        carnumber = carnumber + 1
        if carnumber > 6:
            carnumber = 1
        await asyncio.sleep(1)

start_server = websockets.serve(send_message, "localhost", PORT)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
