# Official - Scalextric Arc BLE Protocol

**Scalextric Arc BLE Protocol**

*(word doc is in "development (dropbox)")*

**Summary**

This document describes the communication protocol between mobile smart device (Android or iOS) and Scalextric ARC powerbase (Arc One, Arc Air or Arc Pro) via Blue Tooth 4.0 (BLE) or above.

There are 3 levels of ARC powerbase. The Arc One just supports analogue mode with up to 2 cars under the control of 2 wired hand controllers. The Arc Air just supports analogue mode with up to 2 cars too, but under control of two wireless hand controllers; The Arc Pro can support both digital mode (up to 6 digital cars) and analogue mode (up to 2 analogue cars), under control by up to 6 wireless hand controllers.

**BLE chip to app (BLE) and vice versa**

The BLE interface consists of two custom and several standard services, which each include multiple characteristics.

**Advertising Packet**

- Device class 7936
- Name “Scalextric ARC  ”
- Service 0x180A (Device Information Service)
- Service 0x3B08 (Scalextric Service)

**Service 0x1800 (Standard): Generic Access Service (GAP)**

- Characteristic 0x2A00 (Standard): Device Name: “Scalextric ARC  ”
- Characteristic 0x2A01 (Standard): Appearance: 833 (Heart Rate Sensor: Heart Rate Belt) (this is the default used by Nordic)
- Characteristic 0x2A04 (Standard): Peripheral Preferred Connection Parameters: 16, 32, 0, 400
    - Minimum Connection Interval (16) 20ms
    - Maximum Connection Interval (32) 40ms
    - Slave Latency (0) None
    - Connection Supervision Timeout Multiplier (400)

**Service 0x1801 (Standard): Generic Attribute Service (GATT)**

- Characteristic 0x2A05 (Standard): Service Changed

**Service 0x180A (Standard): Device Information Service**

- Characteristic 0x2A24 (Standard): Model Number String “Scalextric ARC PRO” (“Scalexric ARC ONE” for Arc One, “Scalextric ARC AIR” for Arc Air)
- Characteristic 0x2A26 (Standard): Firmware Revision String “2.5” (BLE firmware version)
- Characteristic 0x2A27 (Standard): Hardware Revision String “1.0.1”
- Characteristic 0x2A28 (Standard): Software Revision String “2.5”
- Characteristic 0x2A29 (Standard): Manufacturer Name String “Hornby Hobbies Ltd”

**Service 0x1530-1212-efde-1523-785feabcd123 (Nordic) Downloadable Firmware Upgrade (DFU) Service**

- Characteristic 0x1531-1212-efde-1523-785feabcd123 (Nordic) DFU control point
- Characteristic 0x1532-1212-efde-1523-785feabcd123 (Nordic) DFU packet
- Characteristic 0x1534-1212-efde-1523-785feabcd123 (Nordic) DFU revision

**Service 0xFF00 (Custom): Scalextric throttle profile services**

- Characteristic 0xFF01 (Custom) “Profile1”: Throttle profile for car 1 (Write) (17 bytes, changed as needed)
- Characteristic 0xFF02 (Custom) “Profile2”: Throttle profile for car 2 (Write) (17 bytes, changed as needed)
- Characteristic 0xFF03 (Custom) “Profile3”: Throttle profile for car 3 (Write) (17 bytes, changed as needed)
- Characteristic 0xFF04 (Custom) “Profile4”: Throttle profile for car 4 (Write) (17 bytes, changed as needed)
- Characteristic 0xFF05 (Custom) “Profile5”: Throttle profile for car 5 (Write) (17 bytes, changed as needed)
- Characteristic 0xFF06 (Custom) “Profile6”: Throttle profile for car 6 (Write) (17 bytes, changed as needed)

The meaning of the throttle profile characteristics (0xFF01...0xFF06) is as follows:

Byte 0 = the block within the throttle profile (0...3) to update with this data. This lets the app update all 64 bytes of the throttle profile for the car, which is a table stored on the BLE chip that maps the throttle (0...63) to power (0...255).

Bytes 1...16 = the throttle data (0...0xff) for each of 16 adjacent data values in the throttle profile.

Bytes 17...19 = padding (0x00)

**Service 0x3B08 (Custom): Scalextric service**

- Characteristic 0x3B09 (Custom) “Throttle”: Information Characteristic (Notify) (20 bytes, changed many times per second)
- Characteristic 0x3B0A (Custom) “Command”: Command Characteristic (Write) (20 bytes)
- Characteristic 0x3B0B (Custom) “Slot”: Slot characteristic (Notify) (18 bytes, changed several times per second)
- Characteristic 0x3B0C (Custom) “Track”: Track characteristic (Notify)
- Characteristic 0x3B0D (Custom) “CarID”: Car ID characteristic (Write) (1 byte)

**Charactistic 0x3B09 “Throttle”**

This characteristic is sent from the base station to the app in order to inform the app about the throttle positions and other values.

| **Byte** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| 0 | uint8 | packetSequence | This counts up 0...255 with each notification packet sent; it ensures that the characteristic changes often and is thus sent. |
| 1...6 | uint8[6] | throttle | This is the throttle value for each car (0...0x3f)
plus 0x40 if the brake button is pressed,
plus 0x80 if the lane change button is pressed. |
| 7...10 | uint32 | throttleTimestamp | This contains a timestamp of when the throttle packet was last updated, in milliseconds. |
| 11 | uint8 | isDigital | Which mode is the base station in? This byte is the sum of these flags:
0x00 if analog, 0x01 if digital
0x04 if car 1 lane-change button is double tapped
0x08 if car 2 lane-change button is double tapped
0x10 if car 3 lane-change button is double tapped
0x20 if car 4 lane-change button is double tapped
0x40 if car 5 lane-change button is double tapped
0x80 if car 6 lane-change button is double tapped |
| 12 | uint8 | picVersion | Version number of the track CPU firmware (PIC18), for Arc Pro only. |
| 13 | uint8 | baseVersion | Version number of the base controller CPU firmware, not for Arc One. |
| 14...19 | uint8[6] | ctrlVersion | Version number of the firmware of each of the controllers, not for Arc One. |

**Charactistic 0x3B0A “Command”**

This characteristic is used by the app to control the speed of the cars on the track.

| **Byte** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| 0 | uint8 | Command | See below |
| 1,2,3,4,5,6 | uint8[6] | Power | Power multiplier for cars 1 to 6 (0...0x3f)
Plus 0x80 if this value should ignore the throttle position of the controller for this car (equals App controls this car directly, for example during calibration or ghost car). |
| 7,8,9,10,11,12 | uint8[6] | Rumble | Rumble value for cars 1 to 6 (0...0xff), rumble corresponding wireless hand controller. |
| 13,14,15,16,17,18 | uint8[6] | Brake | Brake value for cars 1 to 6 (0...0xff) reserved for use by **scale.it** |
| 19 | uint8 | KERS | Trigger KERS on each car – one bit per car (bit 0 = car 1). |

The commands include:

| **Value** | **Name** | **Meaning** |
| --- | --- | --- |
| 0 | NO_POWER_TIMER_STOPED | To control the powerbase track power off and time stamps of characteristic 0x3B0B reset to 0. Usually it is used in save mode. |
| 1 | NO_POWER_TIMER_TICKING | To control power to track but all speed 0, time stamps zeroed. Usually it is used as ready mode. |
| 2 | POWER_ON_RACE_TRIGGER | To control power to track, time stamps halt. Usually it is used as yellow flag status, ready to resume the game from game halt. |
| 3 | POWER_ON_RACING | To control power to track, time stamps ticking, power outputs follow the throttle levels and the car power bytes. The time stamps update when cars pass the sensors. Usually it is normal game mode. |
| 4 | POWER_ON_TIMER_HALT | To control power off, but time stamps halt. Usually it is used as game halt mode, for example, players want to halt the game when a car runs out off track. |
| 5 | NO_POWER_REBOOT_PIC18 | command 5 causes DFU on PIC18 |

**Characteristic 0x3B0B (Custom) “Slot”: Slot characteristic (Notify)**

This characteristic is sent once per car in a round-robin fashion, to update the app about the details of when each car has most recently passed the start/finish sensor or the end-of-pitlane sensor for each track. Timestamps are relative to when the timer was reset, are in milliseconds, and are stored little-endian.

| **Byte** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| 0 | uint8 | sequence | Number that updates every packet (0...255) |
| 1 | uint8 | car | ID of the car this packet refers to (1...6) |
| 2...5 | uint32 | track1 | Timestamp in ms for passing track 1 start/finish line. |
| 6...9 | uint32 | track2 | Timestamp in ms for passing track 2 start/finish line. |
| 10...13 | uint32 | pitlane1 | Timestamp in ms for passing track 1 end-of-pitlane sensor. |
| 14...17 | uint32 | pitlane2 | Timestamp in ms for passing track 2 end-of-pitlane sensor. |

**Characteristic 0x3B0C (Custom) “Track”: Track characteristic (Notify)**

This characteristic is sent from the base station to the app to inform it of physical problems with the tracks.

| **Byte** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| 0 | uint8 | sequence | Number that increments every packet (0...255) |
| 1 | uint8 | track1 | The status of the first track:
0 = normal
1 = too much current
2 = too low voltage
If the powerbase reports the value 1 or 2, the track protection will be automatically activated by cut off the power to the tracks to avoid damages to hardware (this does not happen in Arc One because there is not hardware power control in Arc One). The power level bytes in 0x3B0A for driving the car will be ignored. If the App receives 1 or 2 in this byte, it should send 4 or 0 to byte 0 of characteristic 0x3B0A to halt mode and save mode to cut off the track power, check the physical problem on the track and cars. If the problem has been fixed, the App can send 3 to byte 0 of characteristic 0x3B0A to resume the game). |
| 2 | uint8 | track2 | The status of the second track (values as with the first track) |
| 3...6 | uint32 | timeStamp | Timestamp in milliseconds of the last problem (or 0 if there are no problems). |

**Characteristic 0x3B0D (Custom) “CarID”: Car ID characteristic (Write) (1 byte)**

This characteristic is set by the app to the track to tell the equipment to set the car id of any digital cars currently on either track.

| **Byte** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| 0 | uint8 | CarID | 0 means nothing. 1...6 means set the track output to be in “Set Car ID” mode rather than the normal speed packets. In that mode, any digital car on the track will have its internal digital ID set to the value (1...6) rather than moving. |