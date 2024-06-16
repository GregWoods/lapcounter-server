import RPi.GPIO as GPIO
import json
import socket
from datetime import datetime
from sys import stdout

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(4,GPIO.OUT)  #HSHAKE1 out to PIC1
GPIO.setup(2,GPIO.IN)   #FLAG1 in from PIC1
GPIO.setup(27,GPIO.IN)   #CARCODE1/1 from PIC1
GPIO.setup(22,GPIO.IN)  #CARCODE1/2 from PIC1
GPIO.setup(17,GPIO.IN)  #CARCODE1/3 from PIC1
GPIO.setup(13,GPIO.OUT)  #HSHAKE2 to PIC2
GPIO.setup(19,GPIO.IN)  #FLAG2 in from PIC2
GPIO.setup(6,GPIO.IN)  #CARCODE2/1 from PIC2
GPIO.setup(5,GPIO.IN) #CARCODE2/2 from PIC2
GPIO.setup(26,GPIO.IN) #CARCODE2/3 from PIC2

GPIO.output(4, False)   #set HSHAKE1 low
GPIO.output(4, True)    #set HSHAKE1 high
GPIO.output(13, False)  #set HSHAKE2 low
GPIO.output(13, True)  #set HSHAKE2 high

carnumber = 1
prevtime = datetime.now()
prevtimelist = [prevtime.timestamp()-3, prevtime.timestamp()-3, prevtime.timestamp()-3, prevtime.timestamp()-3, prevtime.timestamp()-3, prevtime.timestamp()-3]

while True:
    #check FLAG1 and FLAG2 from PICS
    flag1 = GPIO.input(2)
    flag2 = GPIO.input(19)
    while flag1 != 0 and flag2 != 0:  # if neither flag active, keep checking
        flag1 = GPIO.input(2)
        flag2 = GPIO.input(19)

    thistime = datetime.now()
    if flag1 == 0:
        #read data from PIC1
        carcode1 = GPIO.input(27)
        carcode2 = GPIO.input(22)
        carcode3 = GPIO.input(17)
    else:
        #read data from PIC2
        carcode1 = GPIO.input(6)
        carcode2 = GPIO.input(5)
        carcode3 = GPIO.input(26)

    carnumber = 0
    if carcode1 == True: carnumber = carnumber + 1
    if carcode2 == True: carnumber = carnumber + 2
    if carcode3 == True: carnumber = carnumber + 4

    #calculate laptime for this car
    lapsedtime = thistime.timestamp() - prevtimelist[carnumber]
    #if this is a realistic time then send it
    if lapsedtime > 3:
        lapdata = {"type": "lap", "car": carnumber+1, "time": thistime.timestamp()}
        sendlap = json.dumps(lapdata)
        print(sendlap)
        stdout.flush()

    #otherwise it must have been a double bounce so update car laptimer
    prevtimelist[carnumber] = thistime.timestamp()

    #set corresponding HSHAKE bit LOW to say finished reading
    if flag1 == 0:
        GPIO.output(4, False)
        flag1 = GPIO.input(2)
        while flag1 != 1:
            flag1 = GPIO.input(2)
        GPIO.output(4, True)
    else:
        GPIO.output(13, False)
        flag2 = GPIO.input(19)
        while flag2 != 1:
            flag2 = GPIO.input(19)
        GPIO.output(13, True)
