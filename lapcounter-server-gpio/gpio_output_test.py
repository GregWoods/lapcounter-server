#!/usr/bin/python3
import time
import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt


mqtt_host = "172.18.0.3"    # try "mosquitto"

GPIO.setmode(GPIO.BCM)
GPIO.setup(3,GPIO.IN, pull_up_down=GPIO.PUD_OFF)

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    #client.subscribe("$SYS/#")

# The callback for when a PUBLISH message is received from the server.
#def on_message(client, userdata, msg):
#print(msg.topic+" "+str(msg.payload))


print(f"MQTT Host: {mqtt_host}")

client = mqtt.Client()
client.on_connect = on_connect
#client.on_message = on_message


client.connect(mqtt_host)


while True:
    if GPIO.input(3) == GPIO.LOW:
        client.publish("button_pressed", payload=None, qos=0, retain=False)
        print('Button Pressed')
        time.sleep(0.2)
