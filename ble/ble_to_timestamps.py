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
import itertools
import json
import logging
import os
import secrets
import time
from typing import NamedTuple

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
# How hard to chase the first reconnect. See the backoff in run().
RECONNECT_FAST_DELAY = float(os.getenv('BLE_RECONNECT_FAST_DELAY', '1'))
RECONNECT_FAST_WINDOW_S = float(os.getenv('BLE_RECONNECT_FAST_WINDOW', '30'))

MQTT_TIMESTAMP_TOPIC = "car_timestamp"
MQTT_CLOCK_TOPIC = "layer1_clock"

# Plan A (docs/lap-timing-plan.md), confirmed by HW-12 on 2026-09-20: the Throttle
# characteristic's throttleTimestamp is a live reading of the same clock the Slot
# crossings are stamped on, so notifying it gives lapdata a steady stream of
# (clock, counter) samples to anchor against — including while the cars are sitting on
# the grid, which is when lap 1's anchor has to be right. 'none' turns it off, leaving
# only crossings to anchor from (plan C).
clock_heartbeat = os.getenv('BLE_CLOCK_HEARTBEAT', 'throttle').strip().lower()

# Scalextric ARC "slot" GATT characteristic (notify-only). Confirmed against
# github.com/RazManager/ScalextricArcBleProtocolExplorer, which implements
# Scalextric's official ARC BLE protocol doc. Notification payload (18 bytes,
# little-endian):
#   byte[0]      packet sequence
#   byte[1]      CarId, 1-6 — already the digital car ID, no CARCODE bit-decode needed
#   byte[2:6]    TimestampStartFinish1 (uint32 ticks) — physical lane 1 sensor
#   byte[6:10]   TimestampStartFinish2 (uint32 ticks) — physical lane 2 sensor
#   byte[10:18]  pitlane timestamps — unused, this project has no pit lane feature
SLOT_CHARACTERISTIC_UUID = "00003b0b-0000-1000-8000-00805f9b34fb"

# ⚠️ Powerbase timestamps count in 10ms ticks, NOT the milliseconds the protocol doc says.
# Measured on a real ARC Pro on 2026-09-18 (hardware_check.py): four independent checks
# put the device clock at 0.1x wall time when read as ms — HW-04 lap deltas (a 54.08s
# lap read "5.296s"), HW-10's drift over 125 crossings (902,424 ppm = 0.098x), and
# HW-12's throttleTimestamp rate (0.1x), with HW-06's halt arithmetic only consistent in
# ticks. Read as ms, every lap came out ~10x short and fell under MINIMUM_LAP_TIME. It
# applies to both the Slot and the throttleTimestamp values. Every conversion of a device
# value to seconds goes through device_seconds(), including hardware_check.py and the
# mock powerbase, so this is the one place the unit lives.
DEVICE_TICK_S = 0.01


def device_seconds(ticks: int) -> float:
    return ticks * DEVICE_TICK_S

# Throttle characteristic (notify, 20 bytes, "many times per second"):
#   byte[0]      packet sequence
#   byte[1:7]    throttle per car, 0...0x3f, +0x40 brake button, +0x80 lane-change button
#   byte[7:11]   throttleTimestamp (uint32 ticks, see DEVICE_TICK_S) — "when the throttle
#                packet was last updated"
#   byte[11]     isDigital flags, then firmware versions — unused
# Not subscribed to yet. HW-12 in hardware_check.py finds out whether throttleTimestamp is
# a live reading of the same clock as the Slot timestamps; if it is, the lap-timing
# redesign (docs/lap-timing-plan.md) uses it as a clock heartbeat.
THROTTLE_CHARACTERISTIC_UUID = "00003b09-0000-1000-8000-00805f9b34fb"

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
NO_POWER = 0x00


class PowerState(NamedTuple):
    """One Command characteristic write: the powerbase state byte and the per-car power
    multiplier that goes with it. The pair travels together because either one alone is
    ambiguous — POWER_ON_RACING means "cars race" or "cars stand still" depending
    entirely on the multiplier."""
    command: int
    power: int


# ⚠️ Stopping the cars must NEVER stop the powerbase's counter (Greg, 2026-09-20).
#
# The protocol offers no state that cuts power and leaves the timestamps ticking: 0 and 1
# zero them, 2 and 4 freeze them. So stopping the cars via the state byte would break the
# counter mid-race, forcing a new clock at the cut and another at the restart, and every
# lap spanning the stoppage would go through lapdata's anchor instead of being an exact
# counter subtraction.
#
# Holding the multiplier at zero under POWER_ON_RACING instead leaves the counter running
# throughout, so the counter never breaks, no clock changes, and the lap either side of a
# yellow flag is one long lap measured exactly — which is what it really was. Cars sat
# still for 30s of it; that is expected and correct.
#
# ✅ CONFIRMED on a real ARC Pro, 2026-09-20 (HW-03): with a trigger held flat, the car ran
# at 0x3f, slowed distinctly at 0x2f and again at 0x20, and STOPPED at 0x00 — and the
# counter advanced at rate 1.0 through every step, the 0x00 one included. So both halves
# hold: a zero multiplier really does stop the car, and it does it without breaking the
# counter. PowerState(POWER_ON_TIMER_HALT, NO_POWER) remains the fallback if a different
# powerbase or firmware ever disagrees.
#
# Note this leaves the track energised (command 3 keeps power on the rails, which digital
# Scalextric needs for its data signal anyway) — it stops the cars, it does not kill the
# track.
TRACK_RACING = PowerState(POWER_ON_RACING, FULL_POWER)
CARS_STOPPED = PowerState(POWER_ON_RACING, NO_POWER)

# Per car-ID (index 0..5 = car 1..6): last-seen raw StartFinish1/2 values, so a
# notification only turns into a crossing when one of them actually changed —
# the powerbase renotifies the full slot state on any field change, not just laps.
# [None, None] means "not yet seeded since connecting", which is distinct from
# [0, 0] ("seen, and the powerbase's timers are at zero") — see
# handle_slot_notification().
_last_start_finish = [[None, None] for _ in range(6)]
# Which clock each car's baseline above was recorded on. Without this, a timer reset
# would start SIX new clocks rather than one: each car's zeroed packet over the next
# rotation reads as "went backwards" in turn. See handle_slot_notification().
_baseline_clock: list = [None] * 6

# The clock id published alongside every counter. lapdata compares these for equality
# and never parses them, so the shape is ours alone — but the rules are not:
#
#   1. Within one clock, counter_ms advances at real-time rate.
#   2. We start a new clock whenever that stops being true, OR MIGHT HAVE.
#   3. A clock value is never reused, across container restarts included — hence the
#      random per-process part. A restarted ble publishing "ble:1" again would have
#      lapdata comparing its counters against the dead process's.
#
# ⚠️ Rule 2 is now the thing that can go wrong. Missing an event that breaks the counter
# reproduces the old post-halt bug in a new place: lapdata would subtract counters
# across a discontinuity and believe the answer. Every such event needs a test.
_PROCESS_ID = secrets.token_hex(3)
_clock_sequence = itertools.count(1)
_clock = ''


def _new_clock(reason: str) -> str:
    """Start a new clock: the counter has broken continuity, or may have."""
    global _clock
    _clock = f"ble:{_PROCESS_ID}:{next(_clock_sequence)}"
    logger.info(f"New Layer 1 clock {_clock} — {reason}")
    return _clock


_new_clock('process start')

# Commands that break the Slot timestamps' continuity: 0 and 1 zero them, 2 and 4 freeze
# them. Freezing is the easy one to miss — it stops the clock WITHOUT moving it backwards,
# so the backwards-detection in handle_slot_notification() can never catch it.
#
# ⚠️ This project no longer sends any of them: stopping the cars is CARS_STOPPED (command
# 3 at a zero multiplier), which leaves the counter running. The machinery stays because
# it is cheap and the alternative is silent, wrong lap times — a future limp mode, an
# operator's external ARC app, or the HW-03 fallback could all put one of these on the
# wire, and lapdata must see a new clock if any of them does.
#
# ⚠️ HW-11 settles whether command 1 zeroes once and then ticks (its name says so) or
# holds at zero until command 3. It is in this set on the assumption it may hold; if the
# hardware says it ticks, move it out — it then starts a new clock at the write, and
# command 3 after it is not a restart.
_TIMESTAMP_BREAKING_COMMANDS = {NO_POWER_TIMER_STOPPED, NO_POWER_TIMER_TICKING,
                                POWER_ON_RACE_TRIGGER, POWER_ON_TIMER_HALT}

# Whether the powerbase's timestamps are (or may be) frozen. Starts True (and is reset
# on every connect) because we don't know what state the powerbase was left in.
_timestamps_halted = True

# time.monotonic() when the BLE link dropped, or None while connected. Only used to say
# how long we were away in the reconnect log — nothing times a lap with it.
_disconnected_at: float | None = None

# The highest counter value seen from the powerbase, from a crossing or a heartbeat. Its
# job is diagnostic: logged on reconnect so a smaller value afterwards identifies a power
# cycle at a glance, which is otherwise invisible in the logs and is exactly what a
# "we lost two laps" report needs to be checked against.
_last_counter_ms_seen: int | None = None

# Retry for a Command write that fails while connected (a disconnect is covered instead
# by run()'s connect-time write). Without it a rejected CARS_STOPPED would leave cars
# racing until the next race_state transition. Backs off so a powerbase that
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


def counter_ms(device_ticks: int) -> int:
    """A raw powerbase tick count as the milliseconds the car_timestamp contract carries.
    Goes through device_seconds() so DEVICE_TICK_S stays the one place the unit lives."""
    return round(device_seconds(device_ticks) * 1000)


def _note_counter_seen(value_ms: int):
    """Remember the highest counter the powerbase has reported. Diagnostic only — see
    _last_counter_ms_seen."""
    global _last_counter_ms_seen
    if _last_counter_ms_seen is None or value_ms > _last_counter_ms_seen:
        _last_counter_ms_seen = value_ms


def publish_crossing(car_number: int, lane: int, device_ticks: int):
    """Publish the crossing as the powerbase's OWN counter, unconverted.

    Nothing here anchors it to anyone's wall clock any more. The powerbase measured this
    crossing at the sensor, and that number has no reporting jitter in it — the Slot
    characteristic's round-robin delay is in when we HEAR about it, not in the value.
    lapdata subtracts two of these to get a lap time, so the delay cancels out entirely
    and never reaches a lap. The anchor it keeps is only for lap 1.
    """
    _note_counter_seen(counter_ms(device_ticks))
    payload = {"car": car_number, "lane": lane,
               "counter_ms": counter_ms(device_ticks), "clock": _clock}
    mqtt_client.publish(MQTT_TIMESTAMP_TOPIC, payload=json.dumps(payload))
    logger.info(f"car_timestamp: car={car_number} lane={lane} "
                f"counter={counter_ms(device_ticks)}ms clock={_clock}")


def decode_slot(data: bytearray) -> tuple[int, int, int] | None:
    """(car_id, StartFinish1, StartFinish2) in raw ticks from a Slot notification, or None for a
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


def decode_throttle(data: bytearray) -> tuple[int, tuple[int, ...]] | None:
    """(throttleTimestamp in raw ticks, the six raw per-car throttle bytes) from a Throttle
    notification, or None for a packet too short to hold them. Shared with
    hardware_check.py. Doesn't log a short packet: this characteristic notifies many times
    a second, so a misbehaving base would flood the log."""
    if len(data) < 11:
        return None
    return int.from_bytes(data[7:11], 'little'), tuple(data[1:7])


def handle_slot_notification(_sender, data: bytearray):
    decoded = decode_slot(data)
    if decoded is None:
        return
    car_id, timestamp1, timestamp2 = decoded
    idx = car_id - 1

    previous1, previous2 = _last_start_finish[idx]

    # A device timestamp moving BACKWARDS means the powerbase zeroed its timers
    # (commands 0/1, or a power cycle), so counters either side of it can't be compared:
    # a new clock.
    #
    # ⚠️ Only when this car's baseline is from the CURRENT clock. A reset zeroes all six
    # cars, and we see their zeroed packets one at a time over the next round-robin
    # rotation. Without this guard each of the remaining five would read as another
    # backwards jump and start another clock — six clocks for one reset, and every lap
    # that spanned any of them downgraded from an exact counter subtraction to an
    # anchored one.
    if (previous1 is not None and _baseline_clock[idx] == _clock
            and (timestamp1 < previous1 or timestamp2 < previous2)):
        _new_clock(f"powerbase timers went backwards (car {car_id})")

    # Record even a zero — the powerbase really does reset its timers on commands 0/1,
    # and storing that is what lets the next real crossing read as a change.
    _last_start_finish[idx] = [timestamp1, timestamp2]
    _baseline_clock[idx] = _clock

    # First packet EVER seen for this car: that was the baseline, publish nothing. The
    # powerbase keeps counting while nothing is connected (POWER_ON_RACING leaves
    # timestamps ticking — only commands 0 and 1 zero them), so on the first connect of
    # this process it hands us whatever each car's last crossing was, from a race we may
    # not even have been running. Comparing that against "unknown" would read as a change
    # and fake a lap for every car — six phantom laps at startup.
    #
    # ⚠️ This is NOT reached on a reconnect any more (Greg, 2026-09-20): run() keeps the
    # baselines, so a crossing made while the link was down is recognised as a change and
    # published like any other. Those are real laps and must be counted. See run().
    if previous1 is None:
        return

    # Compared against the baseline whatever clock it came from: the powerbase's values
    # run on continuously across a halt, so "changed" still means "crossed". Only the
    # clock the crossing is PUBLISHED on has to be the current one.
    if timestamp1 and timestamp1 != previous1:
        publish_crossing(car_id, 1, timestamp1)
    if timestamp2 and timestamp2 != previous2:
        publish_crossing(car_id, 2, timestamp2)


# At most one layer1_clock sample per this many seconds. The measured Throttle cadence
# is one notification per ~300ms (3.3/s, HW-12 on real hardware 2026-09-20), so on this
# powerbase nothing is ever actually dropped — this only bounds a future firmware that
# notifies faster.
#
# ⚠️ Deliberately a rate limit, NOT the "buffer a 100ms window and publish its
# least-delayed sample" the plan describes. Buffering would hold every sample back by up
# to a window before lapdata could stamp its arrival, which makes every sample LATER —
# and lateness is the only thing that degrades the anchor. Publishing promptly and
# dropping the excess is strictly better for the one job this has.
HEARTBEAT_MIN_INTERVAL_S = 0.1
_last_heartbeat_at: float | None = None


def publish_clock_sample(device_ticks: int):
    """Publish a bare reading of the powerbase's counter, for lapdata to pair with its
    own arrival time.

    This is what makes lap 1 accurate. Crossings anchor the clock too, but a car has to
    cross before they do — and lap 1 is timed from lights-out, which happens before any
    car has crossed anything. Throttle notifications arrive continuously, cars moving or
    not, so by the time the lights go out the anchor has long since converged.

    ⚠️ Published on the SLOT clock, because HW-12 measured throttleTimestamp to be a live
    reading of that same clock (same_clock, live_at_rest, the two anchors agreeing to
    148ms over 10 crossings). If a later powerbase or firmware ever keeps throttle on a
    clock of its own, these samples must carry their own clock id instead — a heartbeat
    from a different clock with a smaller offset would silently drag lapdata's anchor
    down, and a running minimum cannot notice that.
    """
    global _last_heartbeat_at
    now = time.monotonic()
    if _last_heartbeat_at is not None and now - _last_heartbeat_at < HEARTBEAT_MIN_INTERVAL_S:
        return
    _last_heartbeat_at = now
    _note_counter_seen(counter_ms(device_ticks))
    mqtt_client.publish(MQTT_CLOCK_TOPIC, payload=json.dumps(
        {"clock": _clock, "counter_ms": counter_ms(device_ticks)}))


def handle_throttle_notification(_sender, data: bytearray):
    """Throttle notifications are used ONLY as a clock heartbeat here. The throttle
    positions themselves are decoded and discarded — they belong to the fuel and
    jump-start features, which are not implemented (see CLAUDE.md)."""
    decoded = decode_throttle(data)
    if decoded is None:
        return
    publish_clock_sample(decoded[0])


def command_payload(command: int, power: int = FULL_POWER) -> bytes:
    """The 20-byte Command write: byte 0 is the powerbase state, bytes 1-6 the per-car
    power multiplier (not padding — see FULL_POWER), and rumble/brake/KERS (bytes 7-19)
    are genuinely unused. Shared with hardware_check.py, which only ever wants full
    power, hence the default."""
    return bytes([command]) + bytes([power] * 6) + bytes(13)


def _note_command_applied(command: int):
    """Start a new clock when our own write breaks the timestamps' continuity — at the
    halt AND again at the restart. Runs on bleak's loop, the same thread as
    handle_slot_notification(), so it can't interleave with a crossing.

    ⚠️ In normal operation nothing here fires after the connect-time write: a yellow flag
    or a pause sends CARS_STOPPED, which is command 3 at a zero multiplier and does not
    touch the counter (see TRACK_RACING/CARS_STOPPED). This is the safety net for a
    halting command reaching the powerbase some other way.

    Both ends matter, for different reasons. At the **restart**: a halt of D seconds
    leaves the counter D behind real time forever after, so counters either side of it
    are D apart in a way no subtraction can see. At the **halt**: the counter is frozen,
    so heartbeat samples during the halt would keep reporting the same value at later
    and later arrival times — on a fresh clock those are harmless, but on the pre-halt
    clock they would corrupt the anchor that pre-halt laps were timed on.

    Only on a transition. Re-sending POWER_ON_RACING while already racing (which
    handle_race_state does on several transitions) must not burn a clock: the counter
    never stopped, so nothing is discontinuous.
    """
    global _timestamps_halted
    if command in _TIMESTAMP_BREAKING_COMMANDS:
        if not _timestamps_halted:
            _new_clock(f"command {command} halted or zeroed the powerbase timestamps")
        _timestamps_halted = True
    elif _timestamps_halted:
        _new_clock(f"command {command} restarted the powerbase timestamps after a halt")
        _timestamps_halted = False


def _schedule_power_retry():
    global _power_retry_at, _power_retry_delay
    _power_retry_at = time.monotonic() + _power_retry_delay
    logger.warning(f"Retrying the power command in {_power_retry_delay:.0f}s")
    _power_retry_delay = min(_power_retry_delay * 2, POWER_RETRY_MAX_DELAY)


async def _retry_power_if_due():
    """Called once a second from run()'s connected loop. Retries with the power state
    the race calls for NOW, never the state that failed: by the time the retry runs that
    may be stale, and a retried CARS_STOPPED landing after a resume would hold the cars
    on a running race."""
    if _power_retry_at is None or time.monotonic() < _power_retry_at:
        return
    await _write_command_async(_command_for_race_state(_last_seen_race_state))


async def _write_command_async(state: PowerState):
    """Never raises. The Command write is an optional extra on top of this container's
    real job (publishing car_timestamp), so a powerbase that rejects it — no such
    characteristic on ARC One, GATT permission error, bad length — must not be able to
    tear down a working slot-notification subscription. Swallowing here also means the
    fire-and-forget send_command() path can't lose an exception in a dropped future."""
    global _power_retry_at, _power_retry_delay
    if not (_bleak_client and _bleak_client.is_connected):
        logger.warning(f"Cannot write command {state.command}: BLE not connected")
        return
    try:
        await _bleak_client.write_gatt_char(COMMAND_CHARACTERISTIC_UUID,
                                            command_payload(*state))
    except Exception as e:
        logger.error(f"Command characteristic write ({state.command}) failed: {e}")
        _schedule_power_retry()
        return
    _note_command_applied(state.command)
    _power_retry_at = None
    _power_retry_delay = POWER_RETRY_INITIAL_DELAY
    logger.info(f"Command characteristic <- {state.command} at power 0x{state.power:02x}")


def send_command(state: PowerState):
    """Thread-safe entry point for scheduling a Command characteristic write from
    outside bleak's asyncio loop (e.g. paho's on_message thread)."""
    # Read the global ONCE into a local. This runs on paho's thread while run()'s
    # finally clears _ble_loop on the bleak thread, so re-reading it after the None
    # check can hand run_coroutine_threadsafe a None loop — an AttributeError from
    # inside asyncio, plus a never-awaited coroutine.
    loop = _ble_loop
    if loop is None:
        logger.warning(f"Cannot write command {state.command}: BLE not connected")
        return
    asyncio.run_coroutine_threadsafe(_write_command_async(state), loop)


def handle_race_control(data: dict):
    """Translate a race_control command into a Command characteristic write.

    Most transitions map to TRACK_RACING — Layer 1 stays dumb and lapdata's race
    manager is the sole authority on what counts as a real lap, so this only needs to
    keep the powerbase powered and ticking, matching what GPIO always did (it has no
    ability to cut power at all). 'yellow' also keeps full power: the grace period
    (lapdata's race manager, see race_manager.yellow()) lets cars keep racing at
    speed — and their laps keep counting — while lapdata's own timer transitions
    Yellow -> Paused when the grace expires. That transition is never announced over
    race_control, only race_state, so the actual power cut happens in
    handle_race_state() below. 'pause' is the immediate, no-grace stop and stops the
    cars directly here. A limp-mode multiplier between the two is future work.

    Note 'arm' fires several seconds before the actual lights-out "go" (lapdata
    runs the start-light countdown internally, with no race_control message at the
    precise go instant) — see handle_race_state() below for the write that lands
    exactly then.
    """
    command = data.get('command')
    if command == 'pause':
        send_command(CARS_STOPPED)
    elif command in ('prepare', 'arm', 'start', 'yellow', 'resume', 'end'):
        send_command(TRACK_RACING)
    elif command not in ('status', 'reload_lineup'):
        logger.warning(f"Unknown race_control command: {command}")


# Last state seen in a race_state message, so handle_race_state() can detect edges
# instead of rewriting on every message (race_state is republished on every single
# lap crossing).
_last_seen_race_state: str | None = None

# race_state.state -> the Command write it should produce, for states that need one.
# Paused is the one state that stops the cars (a yellow-flag grace expiry, or an
# immediate manual pause, both land here) — Running and Yellow race at full power, and
# laps count in both.
_POWER_STATE_FOR_RACE_STATE = {
    'Running': TRACK_RACING,
    'Yellow': TRACK_RACING,
    'Paused': CARS_STOPPED,
}


def _command_for_race_state(state: str | None) -> PowerState:
    """The power state the powerbase should be in for a race_state. Anything not in the
    table — no race, staged, armed, finished, or not yet heard from lapdata — is full
    power, matching GPIO, which can never cut it."""
    return _POWER_STATE_FOR_RACE_STATE.get(state, TRACK_RACING)


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
    power = _POWER_STATE_FOR_RACE_STATE.get(state)
    if power is not None and state != _last_seen_race_state:
        send_command(power)
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


async def _subscribe_clock_heartbeat(client):
    """Subscribe to Throttle purely as a clock heartbeat (plan A). Never raises: a
    powerbase without this characteristic (or one that refuses the subscription) must
    still count laps, exactly as it does with BLE_CLOCK_HEARTBEAT=none. The cost of
    losing it is a less accurate lap 1, not a broken race."""
    if clock_heartbeat != 'throttle':
        logger.info(f"Clock heartbeat disabled (BLE_CLOCK_HEARTBEAT={clock_heartbeat!r}) — "
                    f"lap 1 will be anchored from crossings alone.")
        return
    try:
        await client.start_notify(THROTTLE_CHARACTERISTIC_UUID, handle_throttle_notification)
    except Exception as e:
        logger.error(f"Could not subscribe to the Throttle characteristic: {e}. Laps will "
                     f"still be counted; lap 1 falls back to anchoring from crossings.")
        return
    logger.info("Subscribed to throttle notifications as a clock heartbeat.")


async def run():
    global _bleak_client, _ble_loop, _timestamps_halted, _power_retry_at, _power_retry_delay
    global _last_heartbeat_at, _disconnected_at
    attempts_since_drop = 0
    while True:
        try:
            address = await find_device_address()
            logger.info(f"Connecting to {address}...")
            async with BleakClient(address) as client:
                if _disconnected_at is None:
                    logger.info("Connected to Scalextric ARC powerbase.")
                else:
                    logger.info(f"Reconnected to Scalextric ARC powerbase after "
                                f"{time.monotonic() - _disconnected_at:.1f}s. Last counter "
                                f"seen before the drop: {_last_counter_ms_seen}ms — a smaller "
                                f"one from here means the powerbase was power-cycled.")
                # ⚠️ The per-car baselines are deliberately KEPT across a reconnect (Greg,
                # 2026-09-20). Clearing them used to force every car's first packet to be
                # swallowed as a fresh baseline, which threw away a real lap: the powerbase
                # reports each car's LAST crossing as absolute state, so a crossing made
                # while we were away is still there when we come back. Remembering what we
                # last saw is what makes it decidable per car, with no phantom-lap risk:
                #
                #   unchanged  -> nothing crossed while away, publish nothing
                #   larger     -> a real crossing while away, publish it
                #   smaller    -> the timers were zeroed, so the powerbase was power-cycled
                #                 and a non-zero value is a real crossing since power-up
                #   None       -> genuinely unknown (first connect of this process), seed
                #
                # A car that crossed TWICE while we were away still loses one: the
                # powerbase keeps only the most recent stamp per car, and no software can
                # recover what it never kept. That is what the fast reconnect is for.
                #
                # Still a new clock, though: the powerbase may have been power-cycled
                # (which zeroes its timer), or halted, or simply carried on — we can't
                # tell, and "might have broken continuity" is exactly what a new clock is
                # for. It may also still be halted from before we dropped, so treat its
                # timestamps as frozen until our first write restarts them.
                _new_clock('connected to the powerbase')
                _timestamps_halted = True
                _last_heartbeat_at = None
                # A retry left over from the last connection is superseded by the
                # connect-time write below.
                _power_retry_at = None
                _power_retry_delay = POWER_RETRY_INITIAL_DELAY

                await client.start_notify(SLOT_CHARACTERISTIC_UUID, handle_slot_notification)
                logger.info("Subscribed to slot notifications — waiting for crossings.")
                await _subscribe_clock_heartbeat(client)

                # Publishing race_control writes is only meaningful once connected —
                # exposing the client/loop here is what lets send_command() (called
                # from paho's thread) reach this asyncio loop via
                # run_coroutine_threadsafe.
                _bleak_client = client
                _ble_loop = asyncio.get_running_loop()
                # Match the race, not a blanket TRACK_RACING: reconnecting while the
                # race is Paused must not set cars moving with marshals on the track.
                # Read the state only after _ble_loop is set, so a race_state edge
                # arriving from here on is written by handle_race_state() instead.
                await _write_command_async(_command_for_race_state(_last_seen_race_state))

                _disconnected_at = None
                attempts_since_drop = 0
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
            if _disconnected_at is None:
                _disconnected_at = time.monotonic()

        # Retry fast at first, then back off. ⚠️ Every second we are not subscribed is a
        # second of crossings the powerbase can only remember one of per car, so the first
        # reconnect after a power cycle is worth chasing hard — a powerbase takes a few
        # seconds to boot and the old flat 5s could idle through most of that. The backoff
        # then stops a base that is simply switched off (overnight, between meets) from
        # filling the Pi's disk with retry lines.
        attempts_since_drop += 1
        delay = (RECONNECT_FAST_DELAY
                 if attempts_since_drop * RECONNECT_FAST_DELAY <= RECONNECT_FAST_WINDOW_S
                 else reconnect_delay)
        if delay != RECONNECT_FAST_DELAY or attempts_since_drop == 1:
            logger.info(f"Retrying in {delay}s...")
        await asyncio.sleep(delay)


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
