# Standalone Scalextric Digital Lap Counter

## Quick Start (Developer)

* see docker compose file and related docs for starting the back end
* nvm use 20.12.2
* npm install
* npm start
* Use the browser developer tools to fix the windows size to 1920x1080 (it can be scaled down via zoom)


## Overview

This project started as a copy of the code supplied by the user "ZoomRnpm startoom" on SlotForum.

This is the post with the latest code. It is in a more recent, compact thread:
https://www.slotforum.com/threads/wifi-raspberry-pi-based-lap-counter-timer.197059/#post-2438259

This thread contains all the technical discussion:
https://www.slotforum.com/threads/raspberry-pi-based-lap-counter-timer.196719/


ZoomRoom's lap counter design consists of:

* A Raspberry Pi 3A
* Connected to a monitor via HDMI
* Also connected to a wireless keyboard + trackpad via USB receiver
* Fittd into a 3D printed case clipped to the edge of a modified half straight track piece
  * which house optical sensors in each lane
  * The sensors are connected to a transistor circuit to amplify and clean up the edges of the signal
  * This optical signal feeds into a PIC microcontroller which converts the "PWM-ish" signal from the car's IR LED into numeric Card IDs 1-6
    * The carID of a car passing the sensor is sent to the Pi over a parallel 3 bit signal via the IO header pins
* A python script reads the car ID from these pins and publishes lap information using a websocket server
* A front web end app is served by the Pi, and is also rendered by the same Pi in a web browser, snd displayed on the connected monitor
  * the web server is just the create-react-app development server at the moment
  * It is also possible to display this web UI in a browser on a separate PC. The added processing power allows for smoother animations in the UI. The Pi struggles with the animations as hardware GPU support was poor in 2022
  * connected to a monitor for display of the race leaderboard. The laps are counted using his home made photodiode sensors (which I suspect use the circuit diagram from the ElectricImages.co.nz website (see the wayback machine here: 

### For Reference

Ian Harding's (MIH) (electricimage.co.nz) was instrumental in the hardware and firmware needed to read the car id using photodiode and PIC firmware. The original documentation is on the wayback machine here: https://web.archive.org/web/20130223083727/http://electricimages.co.nz/(S(zhq2bk45stttoryfmacfyrfs))/SSD_Decoder.ashx

All pages on the electricimages website, indexed here: https://web.archive.org/web/20130222223536/http://electricimages.co.nz/(S(zhq2bk45stttoryfmacfyrfs))/AllPages.aspx
This is still an amazing resource

## My Contribution

Is a revamp of the UI, as I have a pathological hatred of 7 segment LED fonts. I also wanted to learn the javascript React framework which should allow for more UI developments in the future.

I have also added a python script to generate semi-random fake lap data for testing the UI

Before Pic

After Pic

## Current Features of the New UI

* Clearer in-race display
* Fast driver name input
* Predefined race types, to stop debates about whether to race for 50 or 52 laps!
* Only display drivers who are actively driving in the race
* A yellow flag penalty system for deslotted cars

## The Yellow Flag System

The idea is that the wireless keyboard is placed within reach of all drivers. 
When a driver deslots, they hit the spacebar on the keyboard. a 3 seond countdone begins where all drivers can continue racing. Once the countdown finishes all drivers must stop. Laps are not counted at this point.
The deslotted driver retreives their car. The green flag icon is clicked and a brief countdown resumes the race.

Unfortunately we cannot stop cars during a yellow flag event, as we have no control over the track signals. Actually, we could use a smart plug to kill all power to the powerbase. 

So in lieu of stopping cars, we simply stop counting their laps. This means that cunning drivers can gain more than a 3 second advantage if they continue their lap to just before the lap counting sensor. When the race resumes they immediately register a lap. 
In real races, this will result in frequent pileups on the the restart.

## Future enhancements, possibly as options..

* Subtract a lap each time a driver crosses the line during a yellow flag event. (check I don't have that now!) This should be indicated on screen to make it clear who was naughty!
* A "number of lives" system, where each yellow flag reduces a drivers lives by one. Unfortunately drivers will try to avoid the yellow flag if the car is in easy reach, and this could be more of a problem with "lives"
* Reading the track data would be EXTREMELY useful as "zero" throttle for a pre-determined time period could result in an auto yellow flag and penalty for that driver

## Project Structure

TODO: make clear ZoomRoom code, and mine
