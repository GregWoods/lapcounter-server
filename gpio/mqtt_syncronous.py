import time
import paho.mqtt.client as mqtt





# example from : https://pypi.org/project/paho-mqtt/#network-loop
# TODO: read up on "set" data srtucture. Consider using the passed in lapdata timestamp instead of mid.

def on_publish(client, userdata, mid, reason_code, properties):
    # reason_code and properties will only be present in MQTTv5. It's always unset in MQTTv3
    try:
        userdata.remove(mid)
    except KeyError:
        print("on_publish() is called with a mid not present in unacked_publish")
        print("This is due to an unavoidable race-condition:")
        print("* publish() return the mid of the message sent.")
        print("* mid from publish() is added to unacked_publish by the main thread")
        print("* on_publish() is called by the loop_start thread")
        print("While unlikely (because on_publish() will be called after a network round-trip),")
        print(" this is a race-condition that COULD happen")
        print("")
        print("The best solution to avoid race-condition is using the msg_info from publish()")
        print("We could also try using a list of acknowledged mid rather than removing from pending list,")
        print("but remember that mid could be re-used !")

unacked_publish = set()
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_publish = on_publish
client.user_data_set(unacked_publish)
client.connect("10.0.1.188")
# creates a new thread to handle the network loop
client.loop_start()

# TODO: use a while loop to keep checking the local message queue and publish the messages

# Our application produce some messages
msg_info = client.publish("paho/test/topic", "my message", qos=1)
print(f"msg_info={msg_info}")
print(f"msg_info.mid={msg_info.mid}")
unacked_publish.add(msg_info.mid)

msg_info2 = client.publish("paho/test/topic", "my message2", qos=1)
unacked_publish.add(msg_info2.mid)

# Wait for all message to be published
while len(unacked_publish):
    time.sleep(0.1)

client.disconnect()
client.loop_stop()