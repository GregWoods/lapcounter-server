# Standalone Scalextric Digital Lap Counter

AKA: Lapcounter-Server - because it is capable of being used with other systems.

Lapcounter-Server is the software portion of a Scalextric Digital Race Management System.
A combination of hardware and software, which counts laps on a Scalextric Digital slot racing circuit.
It includes a real time leaderboard viewable in a web browser.

For more technical details, please see **readme.developer.md**

## Hardware
The hardware is a Raspberry Pi 3A connected to a 2 lane car id sensor circuit created by [ZoomRoom](https://www.slotforum.com/members/zoomroom.24952/) 
* A Raspberry Pi 3A
* Fitted into a 3D printed case clipped to the edge of a modified half straight track piece
  * which house optical sensors in each lane
  * The sensors are connected to a transistor circuit to amplify and clean up the edges of the signal
  * This optical signal feeds into a PIC microcontroller which converts the "PWM-ish" signal from the car's IR LED into numeric Card IDs 1-6
    * The carID of a car passing the sensor is sent to the Pi over a parallel 3 bit signal via the IO header pins
* [Optional] A Wirelesss Access Point so that the whole system is standalone and transportable (i.e. it is not tied to your home WiFi, and can be run without any internet access)

## Software
The project upon which this is based, is well documented on [slotforum](https://www.slotforum.com/threads/wifi-raspberry-pi-based-lap-counter-timer.197059/). Whilst it was a great accomplishment during a few months of lockdown. I did dislike the UI. So, I developed my own ReactJs based front end. Once that was in a decent state, I started to look at reworking the backend so I could add features not possible with all the logic in the front end code.

![My reworked React JS UI](docs/shakedown.gif)

## Features

* Nice fonts, and nice colours which map to the powerbase/hand throttle colours (hackable)
* F1 style start lights, with additional beep countdown
* Drivers only appear on the leaderboards when they first cross the line, so the screen looks uncluttered if only 2 drivers are racing
* Once the winning driver crosses the line, each driver finishes their lap, then the race is over
    * This can give some odd looking ordering of events, as seen in the GIF, where the race results appear in the following order due to drivers being one or more laps behind - demo results: P1, P6, P3, P4, P2, P5.
    * The logic is correct, as is based on a greater number of laps completed beats less laps completed, and for drivers on the same lap, lower total race time beats higher total race time
* There are just a few predefined race types, because I got tired of drivers debating whether to run a 20 or 25 lap race. Each race type is kept substantially different from the others, with choices intentionally limited (but can be hacked)
* Yellow flag can be triggered by hitting the space bar of an attached keyboard
    * Crossing the finish line under yellow flag results in lap being discarded
    * When a driver deslots, they hit the spacebar on the keyboard. a 3 seond countdone begins where all drivers can continue racing. Once the countdown finishes all drivers must stop. Laps are not counted at this point.
    * The deslotted driver retreives their car. The green flag icon is clicked and a brief countdown resumes the race.
    * Unfortunately we cannot stop cars during a yellow flag event, as we have no control over the track signals.  
        * Actually, we could use a smart plug to kill all power to the powerbase. 
        * In lieu of stopping cars, we simply stop counting their laps. This means that sneaky drivers can gain more than the 3 second advantage if they continue their lap to just before the lap counting sensor. When the race resumes they immediately register a lap. 
            * In real races, this will result in frequent pileups on the the restart, so should probably be disallowed by the marshalls
* Driver with fastest lap of the race has their fastest lap time shown in purple
* Driver names quickly editable (not shown)
* Previously uploaded car images can be quickly selected
* [Coming Soon] A nice UI for uploading the car images


## Notes from the GIF

* The UI to modify the car images was not finished when this was made. The old FSR logo from the Zoomroom original code has been left in for now
* Note that the GIF was generated from fake data, so it takes longer than in most real races for all 6 cars to cross the line and appear on the board


## Future Enhancements

see GitHub Issues




### For Reference

Ian Harding's (MIH) (electricimage.co.nz) was instrumental in the hardware and firmware needed to read the car id using photodiode and PIC firmware. The original documentation is on the wayback machine here: https://web.archive.org/web/20130223083727/http://electricimages.co.nz/(S(zhq2bk45stttoryfmacfyrfs))/SSD_Decoder.ashx

All pages on the electricimages website, indexed here: https://web.archive.org/web/20130222223536/http://electricimages.co.nz/(S(zhq2bk45stttoryfmacfyrfs))/AllPages.aspx
This is still an amazing resource
