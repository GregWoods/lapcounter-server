# Pi Deploy — Dev Setup

> ## ⚠️ SUPERSEDED — do not follow for a race meet
>
> This describes the **old architecture: the Pi as its own WiFi access point**
> (hostapd, `192.168.4.1`, SSID `LapCounter`), reached over Ethernet.
>
> The current setup uses a **Google WiFi puck running OpenWrt as the AP**, with
> the Pi as a wireless *client* on `192.168.8.3`. See
> **[race-network-setup.md](race-network-setup.md)**.
>
> **Do not run `deploy/setup.sh`** on the current Pi. It configures hostapd and a
> NetworkManager AP profile, which would stop the Pi being a WiFi client and cut
> it off from the puck — and the Pi 3A+ has no Ethernet port to recover over.
>
> Kept for reference only.

Test the Raspberry Pi configuration without going through the GitHub Actions build pipeline.
Flash a standard Raspberry Pi OS Lite image, SSH in over ethernet, run the setup steps manually,
then test by connecting a device to the Pi's WiFi.

Ethernet is essential throughout — once the Pi becomes a WiFi AP it is no longer a WiFi client,
so SSH via WiFi to your home network breaks.

---

## 1. Flash Raspberry Pi OS Lite

Open **Raspberry Pi Imager** and before writing, click the settings gear (⚙) and configure:

- **Hostname:** `lapcounter`
- **Enable SSH:** yes, use password authentication
- **Username / password:** `pi` / something you'll remember
- **Do not set WiFi credentials** — you'll connect via ethernet

Write **Raspberry Pi OS Lite (64-bit)** to the SD card.

---

## 2. Boot and SSH in

Plug the Pi into your router via ethernet. Find its IP from your router's DHCP table, or:

```powershell
ping lapcounter.local
```

SSH in:

```powershell
ssh pi@lapcounter.local   # or use the IP directly
```

---

## 3. Copy the deploy files to the Pi

From your Windows machine in the project root:

```powershell
# Create the target directory
ssh pi@lapcounter.local "sudo mkdir -p /opt/lapcounter && sudo chown pi:pi /opt/lapcounter"

# Copy files
scp deploy/compose.pi.yaml pi@lapcounter.local:/opt/lapcounter/compose.yaml
scp deploy/lapcounter.service pi@lapcounter.local:/tmp/lapcounter.service
scp -r mosquitto pi@lapcounter.local:/opt/lapcounter/mosquitto
scp deploy/setup.sh pi@lapcounter.local:/tmp/setup.sh

# Install the systemd service
ssh pi@lapcounter.local "sudo mv /tmp/lapcounter.service /etc/systemd/system/lapcounter.service"
```

---

## 4. Pull Docker images while internet is still available

Once the Pi becomes a WiFi AP it has no internet connection. Pull the images now so the
service finds them cached on first start.

```bash
# On the Pi
curl -fsSL https://get.docker.com | sh
sudo docker compose -f /opt/lapcounter/compose.yaml pull
```

This takes a few minutes on Pi hardware.

---

## 5. Run setup.sh

```bash
# On the Pi
chmod +x /tmp/setup.sh
sudo /tmp/setup.sh
```

Docker is already installed so the `curl | sh` line re-runs harmlessly. Everything else
(hostapd, NetworkManager AP profile, dnsmasq config, service enable) runs fresh.

---

## 6. Reboot

```bash
sudo reboot
```

SSH will drop. The Pi will broadcast the **LapCounter** WiFi network after ~30 seconds.

---

## 7. Test

Connect a phone or laptop to the **LapCounter** WiFi (password: `lapcount3r`).

| Test | Expected |
|---|---|
| `http://gogogo` in browser | Lap counter UI loads |
| `ping 192.168.4.1` | Pi responds |
| `ssh pi@192.168.4.1` | SSH works for further debugging |
| Internet on phone via 5G | Should still work |

---

## Iterating without reflashing

To update the dnsmasq config:

```bash
ssh pi@192.168.4.1

sudo nano /etc/NetworkManager/dnsmasq-shared.d/lapcounter.conf
sudo systemctl restart NetworkManager
```

To update the NetworkManager AP profile (SSID, password, channel):

```bash
sudo nano /etc/NetworkManager/system-connections/LapCounter-AP.nmconnection
sudo nmcli connection reload
sudo nmcli connection up LapCounter-AP
```

To update the Docker stack:

```bash
scp deploy/compose.pi.yaml pi@192.168.4.1:/opt/lapcounter/compose.yaml
ssh pi@192.168.4.1 "sudo docker compose -f /opt/lapcounter/compose.yaml up -d"
```

To view stack logs:

```bash
ssh pi@192.168.4.1 "sudo docker compose -f /opt/lapcounter/compose.yaml logs --tail 50"
```
