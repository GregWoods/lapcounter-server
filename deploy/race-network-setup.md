# Race Meet Network Setup

How to build the standalone, offline network for a lapcounter race meet: an
OpenWrt access point, a Raspberry Pi running the stack, and a captive portal so
attendees can scan a QR code on a poster and land straight on the race pages.

There is **no internet at a race meet**. Everything here is designed to work
with the WAN port unplugged.

## Topology

```
   Attendee phones ─┐
                    ├── WiFi ── Google WiFi puck (OpenWrt) ── [WAN: unplugged on race day]
   Laptop (main UI)─┤            192.168.8.1
                    │            SSID: Scalextric
   Raspberry Pi ────┘            DHCP + DNS (dnsmasq)
   192.168.8.3
   (wireless client - no Ethernet port)
```

The Pi is a **3 Model A+**, which has **no Ethernet port**. It joins the puck's
WiFi as an ordinary client. Everything else follows from that fact — see
"Client isolation" below.

## Addressing

| Thing | Value |
|---|---|
| Puck / gateway / DNS | `192.168.8.1` |
| Pi | `192.168.8.3` (DHCP reservation, not static config) |
| DHCP pool | `192.168.8.50` – `192.168.8.249` |
| SSID | `Scalextric` (WPA2) |
| WiFi password | `racenight2026` |
| Pi wlan0 MAC | `B8:27:EB:B7:5B:58` |
| App URL | `http://192.168.8.3:8087/` |
| API | `http://192.168.8.3:8000` |
| MQTT WebSocket | `ws://192.168.8.3:8080` |
| Captive portal | `http://192.168.8.1/` (served by the **puck**) |
| LuCI admin | `http://192.168.8.1:8080/` (moved off :80) |

The Pi's address comes from a **DHCP reservation on the puck**, not from static
config on the Pi. That survives a reimage and keeps all addressing in one place.

---

## Part 1 — The OpenWrt puck

Hardware: **Google WiFi (Gale), 1st gen**, running OpenWrt 25.12.3
(`ipq40xx/chromium`, kernel 6.12). Only the 1st-gen puck is supported; Nest WiFi
is not, and never will be.

OpenWrt 25.12 replaced `opkg` with **`apk`**. `opkg` does not exist.

### Applying the config

All puck configuration lives in [`openwrt-ap-setup.sh`](openwrt-ap-setup.sh),
which is idempotent and safe to re-run.

```powershell
scp -O deploy/openwrt-ap-setup.sh root@192.168.8.1:/tmp/
ssh root@192.168.8.1 "sed -i 's/\r$//' /tmp/openwrt-ap-setup.sh && sh /tmp/openwrt-ap-setup.sh"
```

Two Windows-specific notes:

- **`scp -O` is required.** Windows' OpenSSH `scp` defaults to the SFTP
  protocol; dropbear on OpenWrt has no `sftp-server`, so plain `scp` fails with
  `/usr/libexec/sftp-server: not found`. `-O` forces the legacy SCP protocol.
- **`sed -i 's/\r$//'`** strips CRLF line endings, which a script edited on
  Windows will otherwise carry into a shell that can't parse them.

### Build mode vs race mode

The captive portal works by resolving **every** DNS name to the Pi. That also
breaks `apt`, `docker pull`, and `apk` for anything using the puck as its
resolver — including the Pi itself.

```sh
HIJACK=0 sh openwrt-ap-setup.sh    # BUILD MODE - real DNS via WAN, no portal
sh openwrt-ap-setup.sh             # RACE MODE  - portal active, offline
```

Run in **build mode** while installing software on the Pi. Switch to **race
mode** once everything is pulled and working.

#### ✅ Automatic, driven by the WAN cable

**Plug the WAN cable in → build mode. Unplug it → race mode.** No commands
needed. Implemented 2026-08-11 and tested in both directions.

| Component | Installed to | Role |
|---|---|---|
| [`openwrt/portal-mode`](openwrt/portal-mode) | `/usr/sbin/portal-mode` | `on` / `off` / `status` |
| [`openwrt/99-portal-mode`](openwrt/99-portal-mode) | `/etc/hotplug.d/iface/99-portal-mode` | fires on WAN `ifup`/`ifdown` |
| [`openwrt/portal-mode-boot`](openwrt/portal-mode-boot) | `/etc/init.d/portal-mode-boot` | fail-safe boot default |

```powershell
scp -O deploy/openwrt/portal-mode      root@192.168.8.1:/usr/sbin/portal-mode
scp -O deploy/openwrt/99-portal-mode   root@192.168.8.1:/etc/hotplug.d/iface/99-portal-mode
scp -O deploy/openwrt/portal-mode-boot root@192.168.8.1:/etc/init.d/portal-mode-boot
ssh root@192.168.8.1 "for f in /usr/sbin/portal-mode /etc/hotplug.d/iface/99-portal-mode /etc/init.d/portal-mode-boot; do sed -i 's/\r$//' \$f; chmod +x \$f; done; /etc/init.d/portal-mode-boot enable"
```

Check or override at any time:

```sh
ssh root@192.168.8.1 "portal-mode status"   # -> "race mode" | "build mode"
ssh root@192.168.8.1 "portal-mode off"      # manual override until next WAN transition
```

**Why the boot script matters.** Hotplug only fires on a *transition*. If the
puck were left in build mode and then booted at a venue with no WAN cable,
neither `ifup` nor `ifdown` would ever fire — the hijack would stay off and the
portal would silently never work, discovered only when nobody can get online. So
the boot script always starts in **race mode**; if the cable is in, the `ifup`
hotplug switches to build mode seconds later. It fails toward "portal works".

Note the WAN interface is named **`mywan`**, not `wan`, in this config — the
hotplug script filters on that name.

<details>
<summary>Original design notes</summary>

#### Planned: make this automatic from WAN link state

Having to remember the toggle in both directions is a genuine trap — forget it
before race day and there is no portal; forget it before an update and nothing
resolves. OpenWrt can drive it from whether the WAN cable is plugged in, via a
hotplug script at `/etc/hotplug.d/iface/99-portal-mode`:

```sh
#!/bin/sh
# WAN up   -> build mode (real DNS, no portal)
# WAN down -> race mode  (hijack everything to the portal)
[ "$INTERFACE" = "mywan" ] || exit 0
case "$ACTION" in
  ifup)   uci -q del_list dhcp.@dnsmasq[0].address='/#/192.168.8.1' ;;
  ifdown) uci -q del_list dhcp.@dnsmasq[0].address='/#/192.168.8.1'
          uci add_list dhcp.@dnsmasq[0].address='/#/192.168.8.1' ;;
  *) exit 0 ;;
esac
uci commit dhcp
/etc/init.d/dnsmasq restart
```

Plug the cable in to update; unplug it for the meet.

</details>

> **Verified against a physical cable pull** (2026-08-11), not just simulated
> `ifdown`/`ifup`. Measured from `logread`:
>
> ```
> 09:07:19  netifd: 'mywan' has link connectivity loss
> 09:07:19  netifd: Interface 'mywan' is now down
> 09:07:23  portal-mode: RACE mode: DNS hijack ON      <- 4s after unplug
> 09:16:27  netifd: 'mywan' has link connectivity
> 09:16:32  portal-mode: BUILD mode: DNS hijack OFF    <- 5s after replug
> ```
>
> Captive portal confirmed working from a client while unplugged. Allow ~5–10 s
> after moving the cable before expecting the change; `portal-mode status`
> reports the current state.

### What the script does

- **Purges home-router leftovers.** The puck arrived carrying a restored backup
  from the home router: 18 static DHCP reservations on `10.0.1.x`. With
  dnsmasq's `expandhosts=1` those become real DNS records, so `lapcounter-server.lan`
  would have resolved to `10.0.1.13` — a black hole on this network.
- **Disables IPv6** (`filter_aaaa=1`, no RA, no DHCPv6, no ULA prefix). This is
  not tidiness. `address=/#/<ipv4>` only answers **A** queries; AAAA leaks
  upstream, so a dual-stack phone runs its connectivity probe over IPv6, fails,
  and never shows the portal.
- **Enables both radios** — 2.4 GHz ch 6 (HT20) and 5 GHz ch 44 (VHT80), same
  SSID, country GB.
- **Reserves `192.168.8.3`** for the Pi's wlan0 MAC.
- **Sets DHCP option 114** (RFC 8910) to the portal URL. Modern iOS and Android
  open this directly on join.
- **Moves LuCI to `:8080`** and runs a second uhttpd instance on `:80` serving
  the captive portal from `/www-portal`.
- **Hijacks DNS** to the router, `192.168.8.1` (race mode only).

### Client isolation must stay OFF

`wireless.ap*.isolate` is set to `0` and **must stay there**. The Pi is a
wireless client, so client isolation — which blocks wireless-to-wireless
traffic — would stop every phone from reaching the Pi. It would only be safe to
enable if the Pi were moved to a wired port, which this hardware cannot do.

### 5 GHz channel

Channel 44 is non-DFS (U-NII-1). **Never use 52–140.** A radar detection event
on a DFS channel silently drops every client mid-race.

### You cannot SSH to the puck from the home LAN

The `wan` firewall zone has `input='REJECT'`. With the WAN plugged into the home
router, the puck is reachable at a `10.0.1.x` address but will refuse SSH. Reach
it on `192.168.8.1` — either over a USB-Ethernet dongle into a LAN port, or by
joining the `Scalextric` WiFi.

### `uci -q delete` and `set -e`

`uci -q delete` still exits **non-zero** when the target doesn't exist; `-q`
only silences the message. Under `set -e` that aborts the script. Every
standalone delete needs `|| true`. The `while uci -q delete ...; do :; done`
loops rely on exactly that non-zero exit to terminate.

---

## Part 2 — Raspberry Pi fresh install

Hardware: **Raspberry Pi 3 Model A+**, armv7l, **512 MB RAM** (~424 MB usable).
OS: **Raspberry Pi OS Lite 32-bit (Debian 13 "trixie")**.

### SD card creation — set the WiFi here

This is the critical step. The Pi 3A+ has **no Ethernet port**, so if WiFi
isn't configured before first boot there is no way to reach the machine except
a hardwired serial/HDMI console.

In **Raspberry Pi Imager**, choose the OS and storage, then open
**Edit Settings** (the gear / "Would you like to apply customisation settings?")
and set:

| Setting | Value |
|---|---|
| Hostname | `lapcounter-server` |
| Username | `greg` |
| Authentication | **Public key** (paste your laptop's `id_*.pub`) |
| Configure wireless LAN — SSID | `Scalextric` |
| Configure wireless LAN — Password | `racenight2026` |
| Wireless LAN country | `GB` |
| Enable SSH | yes |

The **wireless LAN country is not optional** — without it the radio stays
soft-blocked by rfkill and nothing will associate no matter how correct the
credentials are.

The puck must already be broadcasting `Scalextric` when the Pi first boots.
Do Part 1 first.

### Finding the Pi on first boot

It will take a pool address before the reservation applies. Find it from the
puck:

```sh
ssh root@192.168.8.1 "cat /tmp/dhcp.leases"
```

Then `ssh greg@<that address>`. Reboot the Pi once and it will settle onto
`192.168.8.3` from the reservation.

`.local` mDNS names are unreliable here: in race mode the DNS hijack answers
*every* name with `192.168.8.3`, so hostname lookups tell you nothing.

### Network config is owned by netplan-via-NetworkManager

Trixie stores NetworkManager connections as `/etc/netplan/90-NM-<uuid>.yaml`.
`nmcli` edits are written back to those files and **do** persist, so `nmcli` is
the right tool. The connection is named `netplan-wlan0-Scalextric`.

### WiFi power save must be off

The Pi is the server every phone talks to. WiFi power save adds hundreds of
milliseconds of latency and drops packets — it makes the live MQTT leaderboard
look broken.

```bash
sudo nmcli con modify netplan-wlan0-Scalextric 802-11-wireless.powersave 2
sudo nmcli con up netplan-wlan0-Scalextric
```

(`2` = disabled. `iw` is not installed on Pi OS Lite by default.)

### Memory is the real constraint

424 MB usable, plus 423 MB of zram swap (enabled by default on Trixie). The full
stack is eight containers including PostgreSQL 17. Expect to tune Postgres down
(`shared_buffers`, `max_connections`) and watch for the OOM killer.

---

## Part 3 — Docker

```bash
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh
sudo usermod -aG docker greg
# log out and back in for the group to take effect
```

### Image versions — rebuilt 2026-08-11 ✅

The DockerHub images were previously from **January 2025** and predated the
entire `race_meet_manager` branch — the deployed API exposed only
`/api/settings` and `/api/cars`. All five have now been rebuilt and pushed from
the current branch (tag `4e0fc83`), and the deployed API exposes its full
**39 routes**.

```powershell
./build-and-push.ps1     # requires docker buildx + docker login
```

`dbwriter` now has its own `build-and-push-dbwriter.ps1` (previously missing,
which is why it had no published image and no lap persistence in the Pi compose
files). It is included in `build-and-push.ps1`.

If a push fails with `lookup registry-1.docker.io: no such host`, check which
DNS server the build machine is using — with the dongle plugged into the puck,
Windows may route lookups to `192.168.8.1`, which in **race mode** answers every
name with the router's own address. Switch the puck to build mode, or unplug the
dongle, before pushing.

### Deploying a new version

One command, from the repo root:

```powershell
./deploy/deploy.ps1                        # build+push everything, deploy, verify
./deploy/deploy.ps1 -Services react,api    # only what changed - much faster
./deploy/deploy.ps1 -SkipBuild             # just pull+restart on the Pi
./deploy/deploy.ps1 -VerifyOnly            # health check, changes nothing
```

It preflights (Docker running, **puck in build mode**, Pi reachable), builds and
pushes the selected services, runs `pull` then `up -d` on the Pi, and verifies
containers, API route count, the React app and the MQTT WebSocket.

Rough build times: **React ~1 min** (builds natively via `$BUILDPLATFORM`), but
**`api` ~10–15 min** and **`dbwriter` ~8 min** — their C extensions compile under
QEMU for armv7. Use `-Services` to skip what hasn't changed.

The preflight matters: if the puck is in race mode, DNS resolves every name to
the router and `docker push` fails with `lookup registry-1.docker.io: no such
host`. Plugging the WAN cable in fixes it in ~5 s.

### Updating the stack: `pull` first, always

`compose.race.yaml` uses `pull_policy: missing`, which means Docker only fetches
an image when no local copy of that tag exists. Because every service is pinned
to `:latest`, a rebuilt-and-pushed image has the **same tag** as the stale local
one — so `docker compose up -d` on its own will happily keep running the old
code and report success.

```bash
cd /opt/lapcounter
docker compose pull      # REQUIRED - up -d alone will not fetch a new :latest
docker compose up -d
docker compose ps
```

This is the cause of the classic "I pushed the fix but nothing changed" symptom.
Confirm what actually landed with `docker images` and check `CREATED`.

### Pull the images BEFORE going offline

This is the step most easily forgotten. While the puck is in **build mode** with
its WAN plugged in:

```bash
docker compose -f compose.yaml pull
```

Once the puck is in race mode there is no DNS and no internet, so nothing can be
pulled. `pull_policy: missing` in the compose file means Docker will only try on
first run — which will fail offline if the image isn't already local.

Verify with `docker images` before disconnecting.

---

## Part 4 — Captive portal

### How it works

Operating systems detect captive portals by fetching a known URL over **HTTP on
port 80** and checking the response:

| OS | Probe URL | Expects |
|---|---|---|
| Android | `connectivitycheck.gstatic.com/generate_204` | HTTP 204, empty |
| iOS/macOS | `captive.apple.com/hotspot-detect.html` | body containing `Success` |
| Windows | `www.msftconnecttest.com/connecttest.txt` | `Microsoft Connect Test` |

The puck resolves all of these to **itself** (`192.168.8.1`) and answers them
with a `302` to the landing page, which makes the OS declare a captive portal
and pop it open.

### The portal runs on the puck, not the Pi

The Pi has 424 MB of RAM and eight containers; the puck is otherwise idle. So the
portal is served by a second **uhttpd** instance on the puck rather than an nginx
container on the Pi. This costs nothing on the Pi and leaves its port 80 free.

Consequences:

- **LuCI moves to `http://192.168.8.1:8080/`.** Two servers cannot both bind
  `:80`.
- Portal files live in `/www-portal` on the puck; the repo copies are in
  [`portal/`](portal/).

```powershell
ssh root@192.168.8.1 "mkdir -p /www-portal/cgi-bin"
scp -O deploy/portal/index.html root@192.168.8.1:/www-portal/
scp -O deploy/portal/cgi-bin/portal root@192.168.8.1:/www-portal/cgi-bin/
ssh root@192.168.8.1 "sed -i 's/\r$//' /www-portal/cgi-bin/portal && chmod +x /www-portal/cgi-bin/portal"
```

### Why a CGI and not just a 404 page

uhttpd's `error_page` serves a file for unknown URLs, but it keeps the **404**
status. Android treats a bare 404 inconsistently — it may decide the network
simply has no internet and never offer the portal at all. So `error_page` points
at `/cgi-bin/portal`, a three-line shell script that emits a real `302`. That
reliably triggers the portal on iOS, Android and Windows alike.

Verify:

```powershell
# 200 - landing page
(Invoke-WebRequest http://192.168.8.1/ -SkipHttpErrorCheck).StatusCode
# 302 - every probe URL redirects
(Invoke-WebRequest http://192.168.8.1/generate_204 -MaximumRedirection 0 -SkipHttpErrorCheck).StatusCode
```

Probes are plain HTTP, so there are no certificate problems. **Do not serve
HTTPS anywhere on this network** — you cannot get a valid certificate for a
private address offline, and a self-signed one turns every page into a warning
and breaks the portal browser entirely.

### The landing page must be simple

iOS opens captive portals in a cut-down WebView (the "CNA" browser) with its own
cookie jar, no persistence, and unreliable WebSocket support. **The live
MQTT leaderboard will misbehave inside it.**

So `portal.html` is a plain static page with large links and a visible "open in
your browser" instruction. The real app is opened in Safari/Chrome proper.

### The "no internet" nag

Because the probes deliberately fail, phones show "WiFi has no internet access"
and may silently fall back to cellular — which breaks the app. Put a line on the
poster telling people to choose *Stay connected*.

`opennds` is installed on the puck (disabled) as the upgrade path: it shows the
splash, then lets the client through so the probes can be answered *correctly*
afterwards, and the device stops nagging. Only worth enabling if the simple
version proves annoying in practice.

---

## Part 5 — QR codes for the poster

Print **two** codes side by side.

**① Join the WiFi** — encode exactly this string. iOS 11+ and Android 10+ cameras
handle it natively:

```
WIFI:T:WPA;S:Scalextric;P:racenight2026;H:false;;
```

**② Open the page** — encode as a normal URL. This is the fallback whenever the
portal doesn't auto-open, and it costs nothing to print:

```
http://192.168.8.3:8087/
```

Escape any `\ ; , :` characters in the SSID or password with a backslash.

---

## Part 6 — Verification checklist

Run in this order; each step depends on the previous one.

```sh
# On the puck
iwinfo | grep ESSID                      # both bands broadcasting Scalextric
uci show dhcp | grep @host               # ONLY the Pi reservation
nslookup captive.apple.com 127.0.0.1     # race mode: 192.168.8.1 (the router)
nslookup -query=AAAA google.com 127.0.0.1  # must return nothing
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.8.1/            # 200
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.8.1/generate_204 # 302
```

```bash
# On the Pi
ip -4 addr show wlan0                    # 192.168.8.3/24
docker ps                                # all eight containers up
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8087/   # 200 (React)
curl -s http://localhost:8000/openapi.json | head -c 200          # API routes
```

From a phone, with **Forget This Network** first (a device that has joined
before will not re-run the portal — test on both an iPhone and an Android):

1. Scan QR ① → joins `Scalextric`
2. Portal opens automatically
3. Tap through to the app in the full browser
4. **The leaderboard updates** — this is the real test, because it proves the
   MQTT WebSocket on port 8080 is reachable

---

## RAM budget — the binding constraint

The Pi 3A+ has **512 MB** (~424 MB usable) plus ~423 MB of zram swap. The stated
goal is to also fit a **Pi Zero 2 W**, which is likewise 512 MB. Measured figures
live in [ram-analysis.md](ram-analysis.md).

**Measured, not assumed** — and the measurement overturned the obvious guess.
The eight containers total ~159 MB; **Docker's own runtime costs ~114 MB**
(dockerd 34.5, containerd 18.6, and eight `containerd-shim` processes at ~7.6 MB
each). Total demand is ~273 MB against 424 MB physical, with ~108 MB pushed into
zram swap.

Ranked by value:

1. **Replace the React dev-server image — ~45 MB.** The published image is built
   from `Dockerfile.dev` and runs `npm run dev` (Node + Vite, 52.9 MB, plus
   `usePolling` file watching). `react/Dockerfile.prod` already exists and
   produces a static nginx image.
2. **Merge `gpio-1`/`gpio-2` into one container — ~19 MB.** Each costs a Python
   interpreter *and* a 7.6 MB shim.
3. **Replace PostgreSQL with SQLite — ~15–20 MB. Not worth it.** Tuned Postgres
   costs only **21.7 MB**, less than the React dev server, while the port means
   rewriting `dbwriter`'s raw psycopg2 SQL and auditing `next_race.py`.

Options 1 and 2 together save ~64 MB — over three times what dropping Postgres
would yield, at a fraction of the risk. Full figures and method in
[ram-analysis.md](ram-analysis.md).

## Gotchas

- **The clock — already handled in software, no RTC needed.** Neither the Pi nor
  the puck has an RTC and there is no NTP offline, so on a cold boot the Pi's
  time will be wrong. The app solves this: `Home.jsx` calls `GET /admin/clock`
  on mount, compares it against the browser's clock, and offers a sync button
  that POSTs `/admin/sync-clock`. The API runs `date -s`, which sets the **host**
  clock because the container has `cap_add: SYS_TIME` and shares the host time
  namespace.

  **Operational step: open the Home page on the laptop and sync the clock at the
  start of every meet, before the first race.** The laptop keeps correct time via
  its own RTC even offline. Lap timestamps depend on this.

  (`fake-hwclock`, standard on Pi OS, restores the shutdown time at boot, so the
  clock starts plausible rather than at 1970 — but it drifts and is wrong after a
  power cut, so still do the sync.)
- **MQTT is unauthenticated** (`allow_anonymous true`) and ports 1883/8080/8000
  are exposed. Anyone who joins the WiFi can publish `race_control` and
  start/end races. Acceptable on an isolated meet network, but know it.
- **`VITE_ADMIN_PIN` unset means the Admin pages are wide open.**
  `AdminAuthContext.jsx` computes `pinRequired = !!import.meta.env.VITE_ADMIN_PIN`,
  so with no PIN it defaults `isAdmin` to **true**. None of the previous deploy
  compose files set it. It is now passed as a build arg in
  `build-and-push-react.ps1` (currently `1234`). Note the PIN is inlined into the
  JS bundle and is therefore readable by anyone who looks — it is a speed bump
  against a curious attendee, not security.
- **CORS is exact-match.** `REACT_URL` must equal the origin the browser
  actually uses — scheme, host **and** port. Reaching the app by IP when
  `REACT_URL` names a hostname (or a different port) silently breaks every API
  call.
- **`VITE_API_URL` / `VITE_MQTT_URL` are NOT baked in — for this image.**
  `react/build-and-push-react.ps1` builds from **`Dockerfile.dev`**, so the
  published image runs the Vite *dev server* and reads those variables at
  container start. Editing compose is enough. The warning comment in
  `compose.pi.yaml` is wrong for the image that actually exists. This changes if
  the image is ever rebuilt from `Dockerfile.prod` (see RAM, below), where they
  genuinely do become compile-time.
- **`dbwriter` has no published image.** There is no `build-and-push-dbwriter.ps1`,
  and it is absent from `compose.pi.yaml` — so any deployment based on that file
  has **no lap persistence**. `compose.race.yaml` builds it from source on the Pi
  instead.
- **`psycopg2-binary` has no `armv7l` wheel.** On 32-bit Raspberry Pi OS, pip
  falls back to a source build and fails in `python:3.12-slim` with
  *"Getting requirements to build wheel did not run successfully"*.
  `dbwriter/Dockerfile` now installs `gcc` and `libpq-dev` first. This is a
  no-op on amd64/arm64 where the wheel exists, but it makes the first Pi build
  slow (it compiles psycopg2). A **64-bit** Pi OS would avoid the compile
  entirely, since `aarch64` wheels are published — worth considering if the SD
  card is ever rebuilt.
