#To prepare the Raspi SD-CARD...
#  After installing Raspberry Pi OS to the SD card, 
#  Create the folder "/boot/fsr6". Include these extracted folders
#    * FSR6_RPi_code
#    * FSR6_website
#    * My create-react-app's "build" folder contents (must be done after the FSR6 folders)
#    * The contents of my "raspi-install" folder

#This is not a bulletproof installer. 
#TODO: check no duplicates in various config files and services

cd /boot/fsr6
apt install apache2 -y
echo "That's the Apache2 WebServer installed"


# do we need this font stuff?
apt install ttf-mscorefonts-installer
fc-cache -v -f  #looped directory detected ?!?!?!?!


cp FSR6D.html /var/www/html
cp FSR4D.html /var/www/html

#all create-react-app files (unsure if they are all needed)
cp index.html /var/www/html
cp logo192.png /var/www/html
cp logo512.png /var/www/html
cp manifest.json /var/www/html
cp asset-manifest.json /var/www/html
cp favicon.ico /var/www/html
cp robots.txt /var/www/html

mkdir /var/www/html/static
cp static/* /var/www/html/static -r

mkdir /var/www/html/images
cp images/* /var/www/html/images -r
mkdir /var/www/html/fonts
cp fonts/* /var/www/html/fonts -r
mkdir /var/www/html/scripts
cp scripts/* /var/www/html/scripts -r
mkdir /var/www/html/styles
cp styles/* /var/www/html/styles -r
chmod 777 /var/www/html
echo "FSR6 website installed"

echo "enable_uart=1" >> config.txt

cp FSR6webd /usr/local/bin
cp FSR6timer_webd.py /usr/local/bin
cp websocketd /usr/local/bin
cp fsr6.service /lib/systemd/system
chmod 644 /lib/systemd/system/fsr6.service
sudo systemctl daemon-reload
systemctl enable fsr6.service
echo "FSR6 service now enabled"

cp listen-for-shutdown.py /usr/local/bin
cp listen-for-shutdown.sh /etc/init.d
update-rc.d listen-for-shutdown.sh defaults
/etc/init.d/listen-for-shutdown.sh start 
sleep 3
echo "Power ON/OFF button service started"
echo " "
echo "FSR6 INSTALLATION COMPLETED"
echo " "




