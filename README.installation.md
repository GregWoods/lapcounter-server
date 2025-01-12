
# End User Setup- Running on a Raspberry Pi

[see my more recent notes in Docker]

## Install the OS

We do not need a GUI, so I'm using Raspberry Pi OS Lite (64 bit).

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to set up your SD card

* Choose: Raspberry Pi OS Lite (64 bit)
* Apply OS customisation settings: EDIT SETTINGS    
    * Hostname: lapcounter-server
    * Set username and password: <choose your own, keep a record>
    * Configure wireless LAN: <use your WiFi details>
    * Services tab
        * Enable SSH - remote login could be useful later
    * Save
* Would you like to apply OS customisation settings: YES
* Erase card, are you sure: YES

## Boot the Pi, and Login

* On the powered down Pi
* Plug in a monitor and keyboard 
* Insert the microSD card
* Power it up
* Login
* Note: SSH remote login is also possible, but too many steps and pitfalls to add details here

## Download and Run the Installation Script

```
curl -O https://raw.githubusercontent.com/GregWoods/lapcounter-server/main/raspi-setup.sh
chmod 755 raspi-setup.sh
sudo ./raspi-setup.sh
```
