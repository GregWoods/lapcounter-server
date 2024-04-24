import time
import datetime
import os
import json
import paho.mqtt.client as mqtt


mqtt_hostname = os.getenv('MQTT_HOSTNAME')
print(f"MQTT_HOSTNAME: {mqtt_hostname}")

min_lap_time = int(os.getenv('MINIMUM_LAP_TIME')) * 1e9
print(f"MINIMUM_LAP_TIME: {min_lap_time}")


#get a datetime from a time_ns() value
def get_datetime_from_ns(ns):
    return datetime.fromtimestamp(ns/1e9)


# create an initial array of fake previous lap times. All set to 3 seconds ago, in nanoseconds (ints)
prevtimelist = [time.time_ns()-3*1e9 for _ in range(6)]


def send_lap_data(lap_data_json):
    print(f"lap_data_json: {lap_data_json}")
    client.publish("lap", payload=lap_data_json)


def message_received(_client, _userdata, msg):
    topic = msg.topic
    m_decode = str(msg.payload.decode("utf-8","ignore"))
    data = json.loads(m_decode)
    print(data)
    carnumber = data['car']
    caridx = carnumber - 1
    #calculate laptime for this car
    thistime = time.time_ns()
    lapsedtime = thistime - prevtimelist[caridx]
    #if this is a realistic time then send it
    if lapsedtime > min_lap_time:
        # the front end is still expencting a laptime in seconds (not ns)
        lapdata = {"type": "lap", "car": carnumber, "time": thistime/1e9}
        sendlap = json.dumps(lapdata)
        print(sendlap)
        send_lap_data(sendlap)

    # whether the lap time was realistic or a double bounce, or cheat! we still update the prevtimelist
    prevtimelist[caridx] = thistime


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = message_received
client.connect(mqtt_hostname)
# create a new thread to handle the network loop. Also handles reconnecting
client.subscribe("car_timestamp")
client.loop_start()

while True:
    time.sleep(0.001)

client.disconnect()
client.loop_stop()
