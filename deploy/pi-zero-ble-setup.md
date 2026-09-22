# Pi Zero 2 W: BLE-only lapcounter box

How the **Pi Zero 2 W** (`lapcounter-ble`) was built on 2026-09-18 to run lapcounter-server
with the BLE Layer 1 against a Scalextric ARC Pro powerbase. It is a separate box from the
Pi 3A+ race server (`lapcounter-server`, `192.168.8.3`); see
[race-network-setup.md](race-network-setup.md) for that one and for the puck.

Everything below was done by hand. Each step lists the gotcha that made it necessary, since
most of them fail silently.

## 1. Flash the card (Raspberry Pi Imager 2.x)

| Setting | Value |
|---|---|
| Device | Raspberry Pi Zero 2 W |
| OS | Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)**, trixie |
| Hostname | `lapcounter-ble` (not `lapcounter-server`, so it can't be confused with the 3A+) |
| Localisation | Europe/London, **WiFi country GB** |
| User | `greg`, with a password (sudo needs it until step 3) |
| WiFi | `Scalextric` / `racenight2026` |
| Remote access | SSH, **public key**: the laptop's `~/.ssh/id_rsa.pub`, the key `deploy.ps1` uses |

- **32-bit:** it matches the 3A+ and the `linux/arm/v7` images, and uses less of the 512 MB.
  See `ram-analysis.md`.
- **WiFi country is required.** Without it the radio stays rfkill-blocked. The Zero has **no
  Ethernet port**, so a card that can't join WiFi has to be reflashed.
- **An 8 GB card is tight.** With the stack pulled it was 80% full, 1.4 GB free, and the
  `api` image alone is 1.35 GB. Use 16 GB or more.

## 2. First boot and finding it

The puck must already be broadcasting `Scalextric`. First boot takes a few minutes. The Pi
gets a **pool** address, since there is no DHCP reservation for it yet (it came up on
`192.168.8.170`):

```powershell
ssh root@192.168.8.1 "cat /tmp/dhcp.leases"      # look for lapcounter-ble
ssh greg@192.168.8.170
```

## 3. Passwordless sudo

Imager 2.x does **not** give the first user passwordless sudo, unlike older Pi OS images, so
every non-interactive `ssh ... sudo` fails with "a terminal is required". Run this once, in
your own terminal, since it prompts for the password:

```powershell
ssh -t greg@192.168.8.170 "echo 'greg ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/010-greg-nopasswd && sudo chmod 0440 /etc/sudoers.d/010-greg-nopasswd && sudo visudo -c"
```

`visudo -c` validates the file, so a typo can't lock sudo out.

## 4. WiFi power save off

**Not done by Imager, and it was missed at first on this box.** Power save adds hundreds
of ms of latency and drops packets: the live leaderboard lags, and a 44 MB `scp` to the Zero
died with a broken pipe. It takes effect on the next reconnect or reboot:

```bash
sudo nmcli connection modify netplan-wlan0-Scalextric 802-11-wireless.powersave 2
nmcli -g 802-11-wireless.powersave connection show netplan-wlan0-Scalextric   # -> disable
```

## 5. Home WiFi fallback (optional, NOT yet done on this box)

A second, lower-priority profile, so the Pi is reachable at home without the puck. Run it
yourself so the password never leaves your terminal, and never commit real home-network
details to this repo:

```bash
sudo nmcli connection add type wifi ifname wlan0 con-name home-wifi ssid '<home-ssid>' \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk '<home-password>' \
    connection.autoconnect-priority -10 802-11-wireless.powersave 2
```

The negative priority means it only takes over when `Scalextric` is out of range. The web UI
won't work on it (see "Known limitation" below), but SSH will.

## 6. Internet: puck in build mode, then fix the clock

Plug the puck's WAN into the home router: it switches to build mode in ~5 s. In race mode
there is no internet and DNS answers every name with the router.

**Then check the clock.** There is no RTC, and on first boot the clock was 3 days behind
with `System clock synchronized: no`, which makes apt reject repository signatures
("Release file ... is not valid yet"). Kick NTP and wait for it:

```bash
sudo systemctl restart systemd-timesyncd
timedatectl | grep synchronized       # wait for: yes
```

## 7. Docker

```bash
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh && sudo sh /tmp/get-docker.sh
sudo usermod -aG docker greg          # log out and back in
```

(Installed Docker 29.8.1, Compose v5.5.1.) The `lapcounter.service` unit is **not**
installed: every service is `restart: unless-stopped` and Docker starts at boot.

## 8. Stack files

From the repo root on the laptop:

```powershell
ssh greg@192.168.8.170 "sudo mkdir -p /opt/lapcounter && sudo chown greg:greg /opt/lapcounter"
scp deploy/compose.race.yaml greg@192.168.8.170:/opt/lapcounter/compose.yaml
scp -r mosquitto database greg@192.168.8.170:/opt/lapcounter/
ssh greg@192.168.8.170 "sed -i 's/\r$//' /opt/lapcounter/compose.yaml"   # Windows line endings
```

## 9. Images

**`gregkwoods/lapcounter-server-ble` has never been pushed to DockerHub**, and one missing
image makes a bare `docker compose pull` abort the others. Pull the rest by name:

```bash
cd /opt/lapcounter
docker compose pull mosquitto lapdata dbwriter react api database
```

The `ble` image is **side-loaded** from the laptop's working tree, never pushed. Build only
arm/v7 into a tarball, copy it, load it:

```powershell
docker buildx build --platform linux/arm/v7 -t gregkwoods/lapcounter-server-ble:latest `
    --output "type=docker,dest=ble-armv7.tar" ./ble
scp ble-armv7.tar greg@192.168.8.170:/tmp/ble.tar
ssh greg@192.168.8.170 "timeout 300 docker load -i /tmp/ble.tar; rm -f /tmp/ble.tar"
```

- A rebuild takes ~20 s from cache, but **10+ minutes** when the cache is cold: bleak's
  `dbus-fast` compiles under QEMU.
- `docker load` once hung for 12+ minutes after a copy over a flaky link. Hence the
  `timeout`: kill it, delete the tarball and copy again.

## 10. Start the stack and seed the database

```bash
cd /opt/lapcounter
docker compose up -d mosquitto database api lapdata dbwriter react
# pg_isready says "ready" DURING first-run initdb, before lapcounter_server exists, so a
# seed straight after it fails. Wait until the real database answers:
until docker exec database psql -U lap -d lapcounter_server -c 'select 1' >/dev/null 2>&1; do sleep 3; done
docker exec -i database psql -U lap -d lapcounter_server < database/schema.sql
docker exec -i database psql -U lap -d lapcounter_server < database/sampledata.sql
```

A fresh `schema.sql` already has every migration's columns, so `database/migrations/` isn't
needed here. With six containers running, ~219 MB of the 424 MB stays available.

## 11. Bluetooth: unblock it

**Imager's WiFi country unblocks WiFi but leaves Bluetooth rfkill soft-blocked.** Symptom:
`bluetooth.service` is active, but `bluetoothctl show` says `PowerState: off-blocked`, and
bleak fails with `No powered Bluetooth adapters found`. The `rfkill` tool isn't installed,
so use sysfs, and persist it (systemd-rfkill restores the saved state at boot):

```bash
for r in /sys/class/rfkill/rfkill*; do
  [ "$(cat $r/type)" = bluetooth ] && echo 0 | sudo tee $r/soft >/dev/null
done
bluetoothctl power on
for f in /var/lib/systemd/rfkill/*bluetooth*; do echo 0 | sudo tee "$f" >/dev/null; done
bluetoothctl show | grep -E 'Powered|PowerState'     # Powered: yes, PowerState: on
```

## 12. Hardware check, then the `ble` container

With `ble` **not** running (the powerbase takes one BLE connection at a time), and nothing
else connected to the powerbase (e.g. the Scalextric phone app):

```bash
cd /opt/lapcounter
docker run --rm -it -v /var/run/dbus:/var/run/dbus --cap-add NET_ADMIN -v "$PWD:/out" \
    gregkwoods/lapcounter-server-ble:latest python hardware_check.py --report /out/hw-report.json
```

`--only HW-06,HW-07` runs a subset. HW-10 is the 5-minute drift run. Findings are in
[`ble/HARDWARE_VALIDATION.md`](../ble/HARDWARE_VALIDATION.md). The powerbase used was
`EF:2A:C2:EF:D8:AA`: set it as `BLE_ADDRESS` in `compose.yaml` to skip the scan. Then
`docker compose up -d ble`.

**Optional diagnostic:** to see the BLE connection parameters actually negotiated, run
`sudo btmon -w /tmp/x.btsnoop` during a run, then
`btmon -r /tmp/x.btsnoop | grep -i 'connection interval'` (it was 37.5 ms).

## The web UI works on any address (since 2026-09-20)

React derives the API and MQTT addresses from the host that served the page
(`react/src/endpoints.js`) and the API accepts any origin, so `http://192.168.8.170:8087/`
works with no rebuild. Before that change the bundle had `192.168.8.3` compiled in and the
UI timed out on any other Pi.

`deploy.ps1` still targets `greg@192.168.8.3` only, so deploying to this box is by hand
(see step 9). A puck DHCP reservation for its MAC (`2c:cf:67:c2:3d:77`) keeps its address
stable.
