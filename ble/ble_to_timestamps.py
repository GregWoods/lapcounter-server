# Layer 1 alternative to gpio_to_timestamps.py: reads lap crossings straight from a
# Scalextric ARC Pro powerbase over Bluetooth LE instead of two GPIO finish-line
# sensors, and republishes them on the same car_timestamp contract. One container
# replaces both gpio/gpio_to_timestamps.py instances (BLE reports all 6 digital
# car IDs over one connection, gpio needs one process per physical lane sensor).
#
#   export MQTT_HOSTNAME=mosquitto
#   export BLE_ADDRESS=AA:BB:CC:DD:EE:FF   # optional, skips the discovery scan
#   python3 ble_to_timestamps.py
#
# Requires BlueZ's D-Bus socket to be reachable from the container
# (bind-mount /var/run/dbus) and a working Bluetooth adapter on the host.

import asyncio
import json
import logging
import os
import time

import paho.mqtt.client as mqtt      # uses >= 2.0.0
from bleak import BleakClient, BleakScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mqtt_hostname = os.getenv('MQTT_HOSTNAME')
logger.info(f"MQTT_HOSTNAME: {mqtt_hostname}")

# BLE_ADDRESS skips the discovery scan and connects to a known powerbase directly —
# the recommended mode on a dedicated race Pi, since scanning by name needs broader
# Bluetooth capabilities than connecting to a known address.
device_name = os.getenv('BLE_DEVICE_NAME', 'Scalextric ARC')
device_address = os.getenv('BLE_ADDRESS')
scan_timeout = float(os.getenv('BLE_SCAN_TIMEOUT', '10'))
reconnect_delay = float(os.getenv('BLE_RECONNECT_DELAY', '5'))

MQTT_TIMESTAMP_TOPIC = "car_timestamp"

# Scalextric ARC "slot" GATT characteristic (notify-only). Confirmed against
# github.com/RazManager/ScalextricArcBleProtocolExplorer, which implements
# Scalextric's official ARC BLE protocol doc. Notification payload (18 bytes,
# little-endian):
#   byte[0]      packet sequence
#   byte[1]      CarId, 1-6 — already the digital car ID, no CARCODE bit-decode needed
#   byte[2:6]    TimestampStartFinish1 (uint32) — physical lane 1 sensor
#   byte[6:10]   TimestampStartFinish2 (uint32) — physical lane 2 sensor
#   byte[10:18]  pitlane timestamps — unused, this project has no pit lane feature
SLOT_CHARACTERISTIC_UUID = "00003b0b-0000-1000-8000-00805f9b34fb"

# Command characteristic (write-only, 20 bytes): byte 0 selects one of these overall
# powerbase states (power + whether Slot characteristic timestamps tick/halt/reset);
# bytes 1-6 are the per-car power multiplier, 7-12 rumble, 13-18 brake, 19 KERS — see
# ble/reference/Scalextric_ARC_BLE_Protocol.md for the full table.
COMMAND_CHARACTERISTIC_UUID = "00003b0a-0000-1000-8000-00805f9b34fb"
NO_POWER_TIMER_STOPPED = 0
NO_POWER_TIMER_TICKING = 1
POWER_ON_RACE_TRIGGER = 2
POWER_ON_RACING = 3
POWER_ON_TIMER_HALT = 4
NO_POWER_REBOOT_PIC18 = 5

# Per-car power multiplier (Command bytes 1-6). Under POWER_ON_RACING the protocol doc
# is explicit that "power outputs follow the throttle levels *and* the car power bytes",
# so these are NOT inert padding: leaving them at 0 caps every car at zero output and
# no car moves however hard its trigger is pulled. 0x3f is the documented maximum, i.e.
# "throttle passes through untouched" — the GPIO-parity behaviour this Layer 1 wants.
# The 0x80 bit (app drives the car directly, ignoring its controller) stays clear; it's
# what a future ghost-car or fuel-cut feature would set.
FULL_POWER = 0x3F

# Per car-ID (index 0..5 = car 1..6): last-seen raw StartFinish1/2 values, so a
# notification only turns into a crossing when one of them actually changed —
# the powerbase renotifies the full slot state on any field change, not just laps.
# [None, None] means "not yet seeded since connecting", which is distinct from
# [0, 0] ("seen, and the powerbase's timers are at zero") — see
# handle_slot_notification().
_last_start_finish = [[None, None] for _ in range(6)]

# Wall-clock seconds minus powerbase-clock seconds, i.e. what to add to a device
# timestamp to get a unix time on THIS machine's clock. See _device_to_wall().
_clock_offset: float | None = None

# A forward step in THIS machine's clock makes every later (arrival - device_time)
# sample bigger by the step, and _device_to_wall()'s running minimum never follows it
# upward. On the Pi that's the clock being set (NTP, or by hand) after ble connected; in
# dev it's the Docker VM's wall clock catching up after the host sleeps, while the
# simulator's monotonic clock stood still. A normal sample only exceeds the true offset
# by its reporting delay — at most one round-robin rotation, i.e. one Slot packet for
# each of the 6 car IDs in turn. So when every sample for CLOCK_STEP_CONFIRM_S sits more
# than CLOCK_STEP_THRESHOLD_S above the anchor, it isn't delay: re-anchor to the
# smallest of them. The confirmation matters — a BLE stall delivers a late burst and
# then prompt samples again, and re-anchoring on the burst would stamp crossings late
# until a prompt sample dragged the anchor back. It only has to outlast a stall: a long
# enough one drops the connection, and run() re-anchors on reconnect.
# Steps smaller than the threshold go uncorrected. Lap-to-lap deltas don't change, but
# lap 1 is timed from lapdata's clock and reads short by the step, which at ~5s laps
# (under 2s on a test circuit) argues for a threshold as low as the rotation allows.
# 3s is provisional: the protocol doc only says "several times per second", so HW-02
# measures the real rotation — aim for ~2x its worst case.
CLOCK_STEP_THRESHOLD_S = 3.0
CLOCK_STEP_CONFIRM_S = 5.0
_step_run_since: float | None = None   # arrival of the first sample in the current run
_step_run_min: float | None = None     # smallest sample in that run

# Commands that freeze the Slot timestamps. Per the protocol doc, 4 (POWER_ON_TIMER_HALT,
# which a yellow flag's grace expiry sends) is "power off, but time stamps halt".
_TIMESTAMP_HALTING_COMMANDS = {NO_POWER_TIMER_STOPPED, POWER_ON_RACE_TRIGGER, POWER_ON_TIMER_HALT}

# Whether the powerbase's timestamps are (or may be) frozen. A halt of D seconds makes
# every later (arrival - device_time) sample D bigger, and _device_to_wall()'s running
# minimum would keep the smaller pre-halt offset forever: every crossing after the
# resume stamped D seconds early, so laps read short or fall under lapdata's
# MINIMUM_LAP_TIME and vanish. Timestamps never move backwards across a halt, so the
# reset-detection in handle_slot_notification() can't catch it — _note_command_applied()
# re-anchors instead. Starts True (and is reset on every connect) because we don't know
# what state the powerbase was left in.
_timestamps_halted = True

# Retry for a Command write that fails while connected (a disconnect is covered instead
# by run()'s connect-time write). Without it a rejected POWER_ON_TIMER_HALT would leave
# cars powered until the next race_state transition. Backs off so a powerbase that
# rejects every write (ARC One: no Command characteristic) isn't hammered. Only ever
# touched on bleak's loop.
POWER_RETRY_INITIAL_DELAY = 1.0
POWER_RETRY_MAX_DELAY = 30.0
_power_retry_at: float | None = None   # time.monotonic() at which a retry is due
_power_retry_delay = POWER_RETRY_INITIAL_DELAY

# Set once BLE is connected (inside run()), cleared on disconnect. Lets
# handle_race_control(), which runs on paho's own MQTT thread, hand a GATT write
# off to bleak's asyncio client safely via run_coroutine_threadsafe (see
# send_command() below) — bleak's client isn't thread-safe to call directly.
_bleak_client: BleakClient | None = None
_ble_loop: asyncio.AbstractEventLoop | None = None

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def _device_to_wall(device_ms: int, arrival: float) -> float:
    """Convert a powerbase timestamp (ms since its timer was last reset) into unix
    seconds on this machine's clock.

    Why this exists: the Slot characteristic is round-robin across all 6 cars, so a
    crossing is *reported* anywhere from ~0ms to a full cycle after it happened. Using
    notification-arrival time puts all of that jitter straight into every lap time.
    The powerbase measured the crossing itself, at the sensor, in ms — that number has
    no jitter in it, it just needs anchoring to our clock.

    The anchor is a running MINIMUM of (arrival - device_time). Every sample is the
    true offset plus some transport delay, and delay is never negative, so the smallest
    sample seen is the best estimate of the true offset and it converges within a few
    crossings. A constant error in it would cancel out of lap-to-lap deltas anyway;
    keeping it small also keeps lap 1 honest, since that one is timed from
    race_start_time rather than from a previous crossing.

    A minimum can only move down, so a forward step in our own clock is caught
    separately — see CLOCK_STEP_THRESHOLD_S.
    """
    global _clock_offset, _step_run_since, _step_run_min
    candidate = arrival - device_ms / 1000.0
    if _clock_offset is None or candidate < _clock_offset:
        _clock_offset = candidate

    if candidate - _clock_offset <= CLOCK_STEP_THRESHOLD_S:
        _step_run_since = _step_run_min = None
    else:
        if _step_run_since is None:
            _step_run_since, _step_run_min = arrival, candidate
        else:
            _step_run_min = min(_step_run_min, candidate)
        if arrival - _step_run_since >= CLOCK_STEP_CONFIRM_S:
            logger.info(f"Clock stepped forward {_step_run_min - _clock_offset:.1f}s since "
                        "anchoring — re-anchoring the clock offset")
            _clock_offset = _step_run_min
            _step_run_since = _step_run_min = None
    return device_ms / 1000.0 + _clock_offset


def publish_crossing(car_number: int, lane: int, device_ms: int, arrival: float):
    crossing = _device_to_wall(device_ms, arrival)
    payload = {"car": car_number, "timestamp": int(crossing * 1e9), "lane": lane}
    mqtt_client.publish(MQTT_TIMESTAMP_TOPIC, payload=json.dumps(payload))
    logger.info(f"car_timestamp: car={car_number} lane={lane} "
                f"device={device_ms}ms reported {(arrival - crossing) * 1000:.0f}ms late")


def decode_slot(data: bytearray) -> tuple[int, int, int] | None:
    """(car_id, StartFinish1 ms, StartFinish2 ms) from a Slot notification, or None for a
    packet to ignore. Shared with hardware_check.py, so the real powerbase is validated
    against exactly this decoding."""
    # Python slices truncate silently rather than raising, so a short packet would
    # yield a wrong int.from_bytes value that almost certainly differs from the stored
    # previous one — i.e. a fabricated lap. Bail instead. (Documented length is 18;
    # 10 is all we read, since the pitlane timestamps are unused.)
    if len(data) < 10:
        logger.warning(f"Ignoring short slot notification ({len(data)} bytes)")
        return None
    car_id = data[1]
    if not (1 <= car_id <= 6):
        return None
    return car_id, int.from_bytes(data[2:6], 'little'), int.from_bytes(data[6:10], 'little')


def handle_slot_notification(_sender, data: bytearray):
    global _clock_offset

    decoded = decode_slot(data)
    if decoded is None:
        return
    arrival = time.time()
    car_id, timestamp1, timestamp2 = decoded
    idx = car_id - 1

    previous1, previous2 = _last_start_finish[idx]

    # A device timestamp moving BACKWARDS means the powerbase zeroed its timers
    # (commands 0/1 do that). The old anchor now maps device time to a wall clock
    # well in the past, so throw it away and re-anchor from the next crossing.
    if (previous1 is not None
            and (timestamp1 < previous1 or timestamp2 < previous2)):
        logger.info("Powerbase timer reset detected — re-anchoring the clock offset")
        _clock_offset = None

    # Record even a zero — the powerbase really does reset its timers on commands 0/1,
    # and storing that is what lets the next real crossing read as a change.
    _last_start_finish[idx] = [timestamp1, timestamp2]

    # First packet seen for this car since connecting: that was the baseline, publish
    # nothing. The powerbase keeps counting while we're away (POWER_ON_RACING leaves
    # timestamps ticking — only commands 0 and 1 zero them), so it hands us whatever
    # each car's last crossing was. Comparing that against "unknown" would read as a
    # change and fake a lap for every car — six phantom laps on a mid-race reconnect.
    # Cost of seeding: a real crossing in the sub-second before this car's first
    # round-robin packet is missed, which is the far cheaper failure.
    if previous1 is None:
        return

    if timestamp1 and timestamp1 != previous1:
        publish_crossing(car_id, 1, timestamp1, arrival)
    if timestamp2 and timestamp2 != previous2:
        publish_crossing(car_id, 2, timestamp2, arrival)


def command_payload(command: int) -> bytes:
    """The 20-byte Command write: byte 0 is the powerbase state, bytes 1-6 the per-car
    power multiplier at FULL_POWER (not padding — see FULL_POWER), and rumble/brake/KERS
    (bytes 7-19) are genuinely unused. Shared with hardware_check.py."""
    return bytes([command]) + bytes([FULL_POWER] * 6) + bytes(13)


def _note_command_applied(command: int):
    """Track whether the powerbase's timestamps are halted, and throw the clock anchor
    away when a write restarts them — see _timestamps_halted. Runs on bleak's loop, the
    same thread as handle_slot_notification(), so it can't interleave with a crossing."""
    global _timestamps_halted, _clock_offset
    if command in _TIMESTAMP_HALTING_COMMANDS:
        _timestamps_halted = True
    elif _timestamps_halted:
        logger.info("Powerbase timestamps restarting after a halt — re-anchoring the clock offset")
        _clock_offset = None
        _timestamps_halted = False


def _schedule_power_retry():
    global _power_retry_at, _power_retry_delay
    _power_retry_at = time.monotonic() + _power_retry_delay
    logger.warning(f"Retrying the power command in {_power_retry_delay:.0f}s")
    _power_retry_delay = min(_power_retry_delay * 2, POWER_RETRY_MAX_DELAY)


async def _retry_power_if_due():
    """Called once a second from run()'s connected loop. Retries with the power state
    the race calls for NOW, never the command that failed: by the time the retry runs
    that may be stale, and a retried POWER_ON_TIMER_HALT landing after a resume would
    cut power on a running race."""
    if _power_retry_at is None or time.monotonic() < _power_retry_at:
        return
    await _write_command_async(_command_for_race_state(_last_seen_race_state))


async def _write_command_async(command: int):
    """Never raises. The Command write is an optional extra on top of this container's
    real job (publishing car_timestamp), so a powerbase that rejects it — no such
    characteristic on ARC One, GATT permission error, bad length — must not be able to
    tear down a working slot-notification subscription. Swallowing here also means the
    fire-and-forget send_command() path can't lose an exception in a dropped future."""
    global _power_retry_at, _power_retry_delay
    if not (_bleak_client and _bleak_client.is_connected):
        logger.warning(f"Cannot write command {command}: BLE not connected")
        return
    try:
        await _bleak_client.write_gatt_char(COMMAND_CHARACTERISTIC_UUID, command_payload(command))
    except Exception as e:
        logger.error(f"Command characteristic write ({command}) failed: {e}")
        _schedule_power_retry()
        return
    _note_command_applied(command)
    _power_retry_at = None
    _power_retry_delay = POWER_RETRY_INITIAL_DELAY
    logger.info(f"Command characteristic <- {command}")


def send_command(command: int):
    """Thread-safe entry point for scheduling a Command characteristic write from
    outside bleak's asyncio loop (e.g. paho's on_message thread)."""
    # Read the global ONCE into a local. This runs on paho's thread while run()'s
    # finally clears _ble_loop on the bleak thread, so re-reading it after the None
    # check can hand run_coroutine_threadsafe a None loop — an AttributeError from
    # inside asyncio, plus a never-awaited coroutine.
    loop = _ble_loop
    if loop is None:
        logger.warning(f"Cannot write command {command}: BLE not connected")
        return
    asyncio.run_coroutine_threadsafe(_write_command_async(command), loop)


def handle_race_control(data: dict):
    """Translate a race_control command into a Command characteristic write.

    Most transitions map to POWER_ON_RACING — Layer 1 stays dumb and lapdata's race
    manager is the sole authority on what counts as a real lap, so this only needs to
    keep the powerbase powered and ticking, matching what GPIO always did (it has no
    ability to cut power at all). 'yellow' also keeps full power: the grace period
    (lapdata's race manager, see race_manager.yellow()) lets cars keep racing at
    speed, and lapdata's own timer transitions Yellow -> Paused when the grace
    expires — that transition is never announced over race_control, only race_state,
    so the actual power cut happens in handle_race_state() below. 'pause' is the
    immediate, no-grace stop and cuts power directly here. Differentiating further
    states (POWER_ON_RACE_TRIGGER, a limp-mode power multiplier) is future work.

    Note 'arm' fires several seconds before the actual lights-out "go" (lapdata
    runs the start-light countdown internally, with no race_control message at the
    precise go instant) — see handle_race_state() below for the write that lands
    exactly then.
    """
    command = data.get('command')
    if command == 'pause':
        send_command(POWER_ON_TIMER_HALT)
    elif command in ('prepare', 'arm', 'start', 'yellow', 'resume', 'end'):
        send_command(POWER_ON_RACING)
    elif command not in ('status', 'reload_lineup'):
        logger.warning(f"Unknown race_control command: {command}")


# Last state seen in a race_state message, so handle_race_state() can detect edges
# instead of rewriting on every message (race_state is republished on every single
# lap crossing).
_last_seen_race_state: str | None = None

# race_state.state -> the Command write it should produce, for states that need one.
# Paused is the one state that actually cuts power (a yellow-flag grace expiry, or an
# immediate manual pause, both land here) — Running and Yellow keep full power.
_POWER_STATE_FOR_RACE_STATE = {
    'Running': POWER_ON_RACING,
    'Yellow': POWER_ON_RACING,
    'Paused': POWER_ON_TIMER_HALT,
}


def _command_for_race_state(state: str | None) -> int:
    """The power state the powerbase should be in for a race_state. Anything not in the
    table — no race, staged, armed, finished, or not yet heard from lapdata — is full
    power, matching GPIO, which can never cut it."""
    return _POWER_STATE_FOR_RACE_STATE.get(state, POWER_ON_RACING)


def handle_race_state(data: dict):
    """Redundant, precisely-timed write reacting to a race_state transition lapdata
    already computed — belt-and-braces alongside the immediate writes in
    handle_race_control(), and the ONLY place that reacts to the Yellow -> Paused
    grace-expiry, since lapdata drives that transition with its own internal timer
    rather than a race_control message.

    Edge-triggered, so a transition that lands while BLE is disconnected is dropped
    here — run() makes up for it by writing _command_for_race_state() on every connect."""
    global _last_seen_race_state
    state = data.get('state')
    command = _POWER_STATE_FOR_RACE_STATE.get(state)
    if command is not None and state != _last_seen_race_state:
        send_command(command)
    _last_seen_race_state = state


def on_mqtt_message(_client, _userdata, msg):
    try:
        data = json.loads(msg.payload.decode('utf-8', 'ignore'))
        if msg.topic == 'race_control':
            handle_race_control(data)
        elif msg.topic == 'race_state':
            handle_race_state(data)
    except Exception as e:
        logger.error(f"Error handling {msg.topic}: {e}", exc_info=True)


def on_mqtt_connect(client, _userdata, _flags, _reason_code, _properties):
    client.subscribe('race_control')
    client.subscribe('race_state')
    # race_state isn't retained, so ask lapdata for it. Without this, a container
    # restart mid-pause would have no idea the race is Paused, and the connect-time
    # power write in run() would put cars back on full power.
    client.publish('race_control', json.dumps({'command': 'status'}))


def _name_matches(device, adv) -> bool:
    """Prefix match, whitespace-stripped, and NOT `==`.

    The powerbase advertises "Scalextric ARC  " — with two trailing spaces, per the
    spec's Advertising Packet and GAP Device Name (0x2A00) sections. An exact match
    against 'Scalextric ARC' therefore never fires, and the container just loops
    "no device found" forever. Prefix-matching also tolerates a model suffix.

    d.name can be None when the name isn't cached (bleak >= 1.0), so fall back to the
    advertisement's local_name.
    """
    for candidate in (getattr(device, 'name', None), getattr(adv, 'local_name', None)):
        if candidate and candidate.strip().startswith(device_name.strip()):
            return True
    return False


async def find_device_address() -> str:
    if device_address:
        return device_address

    logger.info(f"Scanning for a BLE device whose name starts with '{device_name.strip()}'...")
    device = await BleakScanner.find_device_by_filter(_name_matches, timeout=scan_timeout)
    if device is None:
        raise TimeoutError(
            f"No BLE device named '{device_name.strip()}*' found within {scan_timeout}s. "
            f"Set BLE_ADDRESS to the powerbase's MAC to skip discovery."
        )
    logger.info(f"Discovered '{device.name}' at {device.address}")
    return device.address


async def run():
    global _bleak_client, _ble_loop, _clock_offset, _timestamps_halted, _power_retry_at, _power_retry_delay
    while True:
        try:
            address = await find_device_address()
            logger.info(f"Connecting to {address}...")
            async with BleakClient(address) as client:
                logger.info("Connected to Scalextric ARC powerbase.")
                # Drop every car back to "not yet seeded" — values from before this
                # connection can't be compared against what the powerbase reports now.
                # Same for the clock anchor: the powerbase may have been power-cycled
                # while we were away, which resets its timer to zero. Or it may still
                # be halted from before we dropped, so treat its timestamps as frozen
                # until our first write restarts them.
                for i in range(len(_last_start_finish)):
                    _last_start_finish[i] = [None, None]
                _clock_offset = None
                _timestamps_halted = True
                # A retry left over from the last connection is superseded by the
                # connect-time write below.
                _power_retry_at = None
                _power_retry_delay = POWER_RETRY_INITIAL_DELAY

                await client.start_notify(SLOT_CHARACTERISTIC_UUID, handle_slot_notification)
                logger.info("Subscribed to slot notifications — waiting for crossings.")

                # Publishing race_control writes is only meaningful once connected —
                # exposing the client/loop here is what lets send_command() (called
                # from paho's thread) reach this asyncio loop via
                # run_coroutine_threadsafe.
                _bleak_client = client
                _ble_loop = asyncio.get_running_loop()
                # Match the race, not a blanket POWER_ON_RACING: reconnecting while the
                # race is Paused must not hand marshals on the track a live circuit.
                # Read the state only after _ble_loop is set, so a race_state edge
                # arriving from here on is written by handle_race_state() instead.
                await _write_command_async(_command_for_race_state(_last_seen_race_state))

                while client.is_connected:
                    await asyncio.sleep(1)
                    await _retry_power_if_due()
                logger.warning("BLE connection dropped.")
        except Exception as e:
            # exc_info matters here: this wraps discovery, connection, start_notify and
            # the whole connected lifetime, several bleak exceptions stringify to almost
            # nothing, and a real programming error would otherwise look identical to
            # "powerbase out of range" — on the only diagnostic surface available at a
            # meet with no network.
            logger.error(f"BLE error: {e}", exc_info=True)
        finally:
            _bleak_client = None
            _ble_loop = None

        logger.info(f"Retrying in {reconnect_delay}s...")
        await asyncio.sleep(reconnect_delay)


mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_message = on_mqtt_message

# Only the I/O sits behind the guard, so this module stays importable by
# test_ble_to_timestamps.py. The container (CMD ["python", "ble_to_timestamps.py"])
# runs as __main__ and still connects exactly as before.
if __name__ == '__main__':
    mqtt_client.connect(mqtt_hostname)
    # create a new thread to handle the network loop. Also handles reconnecting
    mqtt_client.loop_start()

    asyncio.run(run())
