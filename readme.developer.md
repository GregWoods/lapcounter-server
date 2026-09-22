# LapCounter-Server - Developer Readme

See readme in the individual sub-project folders for instructions on how to build and run locally, and how to push updated docker images to dockerhub.

For the full technical reference — MQTT topic contracts, the database schema, the race lifecycle, deploy scripts — see **CLAUDE.md** (and `api/CLAUDE.md`). This file is a lighter, narrative overview.

## Quick Start

Local development using docker

```
docker compose -f compose.dev.yaml up --build
```

React works with hot module reloading.

```
http://localhost:8088
```

Suggest using the browser's developer tools to set up a new custom device which runs at a resolution of 1920x1080. Whilst other resolutions may work, there has been a lot of hardcoded css to make it work well at this resolution.

## Project Structure

This project is built in a very modular way, making use of several Docker containers. Some, such as the MQTT broker (Eclipse Mosquitto) and PostgreSQL, are well known public projects.
The lap counter code itself is split amongst several containers. These are outlined below.


## Layer 1 - GPIO or BLE

This layer runs on a Raspberry Pi (or a simulated version, for development off the Pi). It reads raw car-crossing data and publishes it to MQTT under the topic **car_timestamp**, plus a bare counter heartbeat under **layer1_clock**. Two interchangeable implementations exist — exactly one runs at a time:

* **`gpio`** — reads two physical optical sensors (one per lane) via the Pi's GPIO pins, using edge-detection interrupts. Runs as two containers, one per lane.
* **`ble`** — talks to a Scalextric ARC Pro powerbase over Bluetooth LE instead, reading all 6 digital car IDs from one container. This is now the default Layer 1 on the live Pi (`gpio` is the fallback), though newer and less battle-tested.

Both publish the same contract regardless of which is running — nothing above Layer 1 knows or cares which one is in use:

```json
{"car": 2, "lane": 1, "counter_ms": 5123456, "clock": "ble:e3ac9f:3"}
```

`counter_ms` is that Layer 1's own hardware counter at the moment of the crossing — never a wall clock — and `clock` identifies which continuous run of that counter it belongs to (it changes whenever the counter could have discontinuities: a reset, a reconnect, a power cycle). Lap times come from subtracting two `counter_ms` values on the same `clock`, which is what makes them immune to MQTT latency and clock drift. See CLAUDE.md for the full contract.

Mocked versions of both (`mocked-gpio`, `mocked-ble`) run without any hardware, for development.


## Layer 2 - lapdata

Subscribes to `car_timestamp` (and `layer1_clock`), and owns the entire race: positions, lap counts, fastest laps, the F1-style start-light sequence, yellow flags, session/race lifecycle. It's the race manager, not just a data transformer.

It publishes:
* **`lap`** — every crossing, normalised, with no race context (optional, for display).
* **`driver_lap`** — only when a crossing counts as a real lap, with full context. This is what the DB writer persists.
* **`race_state`** — the full computed race state, after every crossing and every internal timer tick (start lights, yellow countdown, etc.). Every display subscribes to this and renders it directly.

It also subscribes to **`race_control`** — commands (`prepare`, `arm`, `start`, `yellow`, `pause`, `resume`, `end`, ...) that any client can publish, and POSTs race start/finish back to the API itself, so persistence doesn't depend on a browser being open.


## Layer 3 - api

A Python API, built with **FastAPI**, backed by **PostgreSQL** (via the SQLModel ORM). REST only — meetings, sessions, drivers, race queue management — it holds no race logic of its own; that's lapdata's job (see CLAUDE.md: "queries are HTTP, events are MQTT"). Auto-generated docs at `/docs`.

A separate small service, **dbwriter**, subscribes to `driver_lap` directly and writes lap/race results straight to PostgreSQL — it doesn't go through the API.


## Layer 4 - react

The web frontend. In development it's served by Vite's dev server with hot reloading — port 5173 inside the container, mapped to `:8088` on the host; in production it's a static build served by nginx.

It's a pure display and control layer: it subscribes to `race_state` over an MQTT WebSocket bridge and renders it directly, and publishes `race_control` commands for the operator's actions (start/pause/end a race, etc.) — it holds no race logic of its own. Routes include the leaderboard (`/currentrace`), the operator's race control panel (`/racecontrol`), lineup management (`/nextrace`), and meeting/session administration (`/meetings`).


# Why this Project?

The goal is that multiple clients can subscribe to this data. In theory, we could have multiple web browsers connected over WiFi. Each driver could have their own custom display on their phones (3D printed throttle-top phone holder anyone?) showing their personal lap times and relative positions to the driver in front and behind. We could also have additional client hardware displaying other useful info around the track. Hardware start lights, green, yellow, red flag illuminated boards could all be set up with a simple connection to a web page served from one of the containers running on the Pi. Old mobile phones could be put to use, as could ESP32 based gadgets. There are lots of possibilities.

For example, we could have the standard leaderboard shown on a large screen TV. But we could have as many of these as we wanted. Instead of running the browser in the Pi itself (which prevents us using fancy CSS animations, due to lack of processing grunt), we use separate laptops, PCs and other Raspi's to connect to the server.

The current ZoomRoom system has the back end python code sending very basic data. It knows nothing about the state of the race. The start, stop, pausing of the race, as well as management of the drivers and cars, were all done in the browser in the original design (pure JS for the original ZoomRoom code, then React JS in my rewrite). That's exactly what moved into the backend: lapdata now owns race state, the API and PostgreSQL persist race meets, sessions and results for later analysis, and a browser refresh no longer kills the current race.

None of this is tied to the ZoomRoom hardware... it just proved to be a convenient platform for experimenting. Any car ID sensors which can attach to a Raspberry Pi would work — the BLE Layer 1 talking to a Scalextric ARC Pro powerbase is the proof of that. Any standalone sensor would work too, as long as it has network access and can publish MQTT messages (RTC clock syncing would be needed for any sensor which sends time-critical data — see the `clock`/`counter_ms` contract above).


# Why Use Docker?

I realise the Docker approach could sound pretty repulsive to anyone who works directly with Assembly or C/C++/Rust on a microcontroller. I've previously experimented with all 3 languages on a mix of AVR, PIC and 32 bit Arm Cortex CPUs, and still feel the Docker approach has adavantages in terms of speed of development and modularity. Obviously it will take some testing to determine if the weight of an entire Linux OS, plus Docker, plus containers can handle it all. In this system, remember that the Pi itself is not reading Car LED pulses directly — either the GPIO signal is offloaded onto a microcontroller (the original ZoomRoom hardware) or the whole thing is read over Bluetooth LE from the powerbase (the BLE Layer 1).

The timing critical part is making sure the signal is not missed, delayed or colliding with the signal from a second car in the other lane. The GPIO Layer 1 uses edge detection interrupts rather than polling, so I'd expect it to be pretty responsive; the BLE Layer 1 relies on the powerbase's own hardware counter for that instead (see the `clock`/`counter_ms` contract above), specifically so that MQTT delivery delay can never corrupt a lap time.

In the end, for me, whilst I would like 100% reliability even for the 1 in a million edge case... for the kind of social race meets with friends and kids, my main motivation is the ability to easily add features to the race management system.

All the code is public.


# Development Methodology

Docker all the way! See CLAUDE.md's "Development Commands" for the day-to-day workflow — the dev stack (`compose.dev.yaml`), running tests, and the important note that `lapdata` does **not** hot-reload (it needs an explicit `docker compose restart lapdata` after editing its code).


# Running on the Raspberry Pi

The full deploy flow — building and pushing images, choosing GPIO vs BLE as Layer 1, and verifying the deploy — is `./deploy/deploy.ps1`. See CLAUDE.md's "Layer 1 hardware options" section and `deploy/deploy.ps1`'s own header comment for the details; it's a single script specifically because a manual deploy is otherwise ~20 separate commands with real footguns (running two Layer 1s at once double-counts every lap).


## Developer - Build & Push Docker Images

Once it is all working locally, build and push every service's multi-platform image to DockerHub:

```powershell
./build-and-push.ps1
```

Each service also has its own `build-and-push-<service>.ps1` (see the sub-project folders) if you only need to push one.


# Testing Mosquitto

The dev stack already runs Mosquitto in its own container, so the simplest way to watch or inject MQTT traffic is straight from inside it — no separate client install needed:

```
docker exec mosquitto mosquitto_sub -t race_state -v
docker exec mosquitto mosquitto_pub -t race_control -m '{"command":"status"}'
```

(Use single quotes around JSON payloads, and separate `docker exec` calls rather than nesting quotes.) See CLAUDE.md's "Development Commands" section for worked examples against the actual current topics (`race_state`, `race_control`, `driver_lap`, etc.) — the topic table there is the authoritative contract.

If you'd rather use a client on your own machine instead of inside the container, `mqttx` (GUI/CLI) or `mosquitto_sub`/`mosquitto_pub` from `mosquitto-clients` (`apt install mosquitto-clients`) both work fine against `localhost:1883`.
