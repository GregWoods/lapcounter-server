#!/bin/bash
set -e

# ── Customise these before building the image ────────────────────────────────
WIFI_SSID="LapCounter"
WIFI_PASSWORD="lapcount3r"   # min 8 characters
WIFI_COUNTRY="GB"            # ISO 3166-1 alpha-2 country code
WIFI_CHANNEL=6               # 1–11 for 2.4 GHz
PI_IP="192.168.4.1"
# ─────────────────────────────────────────────────────────────────────────────

# Hostname — Pi is reachable at http://lap or http://lapcounter on the race network
echo "lapcounter" > /etc/hostname
sed -i 's/raspberrypi/lapcounter/g' /etc/hosts

# Install Docker
curl -fsSL https://get.docker.com | sh

# hostapd is required as the backend for NetworkManager's AP mode
apt-get install -y --no-install-recommends hostapd chrony

# WiFi regulatory domain — must be set or the radio won't transmit
echo "REGDOMAIN=${WIFI_COUNTRY}" > /etc/default/crda

# NetworkManager WiFi AP connection profile.
# method=shared tells NM to run a DHCP server and enable IP forwarding
# automatically — no separate dnsmasq install needed for DHCP.
install -m 600 /dev/null /etc/NetworkManager/system-connections/LapCounter-AP.nmconnection
cat > /etc/NetworkManager/system-connections/LapCounter-AP.nmconnection << EOF
[connection]
id=LapCounter-AP
uuid=4a0e3b2c-1f7d-4e8a-9c6b-5d2f1a8e0b3c
type=wifi
autoconnect=true
interface-name=wlan0

[wifi]
mode=ap
ssid=${WIFI_SSID}
band=bg
channel=${WIFI_CHANNEL}

[wifi-security]
key-mgmt=wpa-psk
psk=${WIFI_PASSWORD}

[ipv4]
method=shared
address1=${PI_IP}/24

[ipv6]
method=disabled
EOF

# DNS: resolve the lap counter's hostname to the Pi's IP.
# Using a plain hostname (no .local suffix) avoids Windows routing .local
# queries through mDNS instead of the configured DNS server.
# Unknown domains return NXDOMAIN so cellular DNS takes over — internet
# via 5G still works on phones while connected to this WiFi network.
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
cat > /etc/NetworkManager/dnsmasq-shared.d/lapcounter.conf << EOF
address=/gogogo/${PI_IP}
dhcp-option=42,${PI_IP}
EOF

# NTP server — serves the Pi's own clock to connected clients.
# local stratum 10 means "I have no upstream sync but will serve time anyway".
# Clients that respect DHCP option 42 (mostly Linux/Android) will sync to this.
cat >> /etc/chrony/chrony.conf << EOF

local stratum 10
allow 192.168.4.0/24
EOF

systemctl enable chrony

# Enable SSH for troubleshooting (credentials set via Raspberry Pi Imager)
systemctl enable ssh

# Enable the Docker stack service
systemctl enable lapcounter.service

# Allow the default pi user to run Docker without sudo
usermod -aG docker pi || true

mkdir -p /opt/lapcounter/data

apt-get clean
rm -rf /var/lib/apt/lists/*
