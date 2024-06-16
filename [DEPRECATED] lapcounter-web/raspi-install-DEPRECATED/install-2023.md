# 2023 Install Guide
  
## Prerequisites

* Note: By "laptop" I mean your development PC/Mac
* We use the LapCounter code from Github
* The Raspi is already setup with Ubuntu
    * Hostname is "lapcounter"
    * SSH server is running on the Pi (usually part of Ubuntu setup)
* You can SSH into the pi from Windows Terminal on your laptop

### Clone the code from GitHub

#### On the Pi (via SSH)

One-off setup
```
ssh-keygen 
cd ~/.ssh
tail id_rsa.pub
```
* Then copy the key from Windows Terminal


#### On the laptop

* In a browser, login into GitHub -> Settings -> SSH & GPT Keys
* Create new SSH key
* Give it a sensible name, e.g.  "Lapcounter Rpi3A"
* Paste the public key data into the textbox
* Save

#### Back on the Pi (SSH)

```
cd ~
sudo cp FSR6_RPi_code/fsr6.service /lib/systemd/system
sudo chmod 644 /lib/systemd/system/fsr6.service
sudo systemctl daemon-reload
sudo systemctl enable fsr6.service
echo "FSR6 service now enabled"

# very useful... list autostart services
systemctl list-unit-files --type=service --state=enabled
# List processes using a port
sudo netstat -lntp | grep -w ":8093"

```

References

https://www.digitalocean.com/community/tutorials/how-to-use-systemctl-to-manage-systemd-services-and-units
https://losst.pro/en/how-to-configure-service-to-start-automatically-in-linux


Procedure

With the Rasp