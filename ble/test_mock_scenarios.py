"""End-to-end scenarios: the real ble_to_timestamps.run() against the simulated powerbase
(mock_powerbase) through the fake bleak (mock_bleak). Step 4 of docs/mocked-ble-plan.md.

test_ble_to_timestamps.py covers each piece in isolation. These cover the pieces together,
across the connected lifecycle: connect, seeding, clock anchoring, Command writes, drops
and retries.

race_control and race_state are delivered from a worker thread, as paho does, so the
run_coroutine_threadsafe handoff into bleak's loop is exercised too.

They run in real time, a few seconds each. run()'s connected loop polls once a second,
and speeding that up would need a test hook in production code, which the plan rules out.
"""
import asyncio
import contextlib
import json
import random
import sys
import time
import types

import pytest


def _stub(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules.setdefault(name, module)


_stub('paho')
_stub('paho.mqtt')
_stub(
    'paho.mqtt.client',
    Client=lambda *a, **k: types.SimpleNamespace(publish=lambda *a, **k: None),
    CallbackAPIVersion=types.SimpleNamespace(VERSION2=2),
)
_stub('bleak', BleakClient=object, BleakScanner=object)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import ble_to_timestamps as ble  # noqa: E402
import mock_bleak  # noqa: E402
import mock_powerbase as mp  # noqa: E402

QUICK_LAPS = mp.LapModel(min_lap_s=0.5, ability_range_s=0.2, lap_spread_s=0.1,
                         outlier_chance=0, lane_change_chance=0.3)
SLOT_INTERVAL_S = 0.01
HALT_S = 2.0
# How late a published stamp may be: the anchor's smallest reporting delay so far, at most
# one 6-packet round-robin cycle. Generous, because Windows sleeps in ~15ms steps. A stale
# anchor after a halt puts a stamp HALT_S early instead, far outside this.
MAX_STAMP_LATE_S = 0.25


@pytest.fixture
def harness(monkeypatch):
    sent = []
    monkeypatch.setattr(ble, 'mqtt_client', types.SimpleNamespace(
        publish=lambda _topic, payload: sent.append(json.loads(payload))))

    # Every published crossing with the device ms it came from, so it can be matched to
    # the crossing the simulator actually made.
    records = []
    real_publish_crossing = ble.publish_crossing

    def recording_publish_crossing(car, lane, device_ms, arrival):
        real_publish_crossing(car, lane, device_ms, arrival)
        records.append((car, lane, device_ms, sent[-1]['timestamp'] / 1e9))

    monkeypatch.setattr(ble, 'publish_crossing', recording_publish_crossing)

    # Disconnected, never-connected module state, as at container start.
    monkeypatch.setattr(ble, '_last_start_finish', [[None, None] for _ in range(6)])
    monkeypatch.setattr(ble, '_clock_offset', None)
    monkeypatch.setattr(ble, '_timestamps_halted', True)
    monkeypatch.setattr(ble, '_power_retry_at', None)
    monkeypatch.setattr(ble, '_power_retry_delay', ble.POWER_RETRY_INITIAL_DELAY)
    monkeypatch.setattr(ble, '_last_seen_race_state', None)
    monkeypatch.setattr(ble, '_bleak_client', None)
    monkeypatch.setattr(ble, '_ble_loop', None)
    monkeypatch.setattr(ble, 'device_address', None)     # exercise the scan
    monkeypatch.setattr(ble, 'reconnect_delay', 0.05)
    monkeypatch.setattr(ble, 'BleakClient', mock_bleak.FakeBleakClient)
    monkeypatch.setattr(ble, 'BleakScanner', mock_bleak.FakeBleakScanner)

    # clock=time.time, so the simulator's record of when a car crossed is directly
    # comparable with the unix-seconds stamp ble publishes.
    powerbase = mp.SimulatedPowerbase(cars=3, clock=time.time, rng=random.Random(11),
                                      lap_model=QUICK_LAPS)
    applied = []
    real_apply = powerbase.apply_command

    def recording_apply(payload):
        real_apply(payload)
        applied.append(payload[0])

    powerbase.apply_command = recording_apply
    faults = mock_bleak.Faults()
    mock_bleak.configure(powerbase, faults=faults, slot_interval_s=SLOT_INTERVAL_S)

    return types.SimpleNamespace(powerbase=powerbase, faults=faults, applied=applied, records=records)


@contextlib.asynccontextmanager
async def ble_running():
    task = asyncio.create_task(ble.run())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def eventually(predicate, what: str, timeout: float = 6.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f'Timed out waiting for {what}')
        await asyncio.sleep(0.01)


def from_paho(handler, data: dict):
    """Deliver an MQTT message on another thread, as paho's network loop does."""
    return asyncio.to_thread(handler, data)


def stamp_errors(h) -> list[float]:
    """Published stamp minus when the car really crossed, for every published crossing.
    A crossing the simulator never made is a phantom lap and fails outright."""
    truth = {(car, lane, device_ms): at for car, lane, at, device_ms in h.powerbase.crossings}
    errors = []
    for car, lane, device_ms, stamp in h.records:
        assert (car, lane, device_ms) in truth, \
            f'Phantom lap: car {car} lane {lane} at device {device_ms}ms never crossed since connecting'
        errors.append(stamp - truth[(car, lane, device_ms)])
    return errors


def assert_stamps_true(h):
    errors = stamp_errors(h)
    # Never early (beyond ms rounding), and late by at most a reporting cycle.
    bad = [round(e, 3) for e in errors if not -0.005 <= e <= MAX_STAMP_LATE_S]
    assert not bad, f'{len(bad)} of {len(errors)} stamps off by (s): {bad}'


# ------------------------------------------------------------------ scenarios

def test_lap_times_stay_true_across_a_halt_and_resume(harness):
    """Review item 1 end to end: the powerbase clock pauses through POWER_ON_TIMER_HALT,
    so without the re-anchor every post-resume crossing is stamped HALT_S early. The
    powerbase starts with retained timestamps, so this also proves seeding on connect."""
    h = harness

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.applied == [ble.POWER_ON_RACING], 'the connect-time power write')
            await eventually(lambda: len(h.records) >= 3, 'crossings before the halt')

            await from_paho(ble.handle_race_control, {'command': 'pause'})
            await eventually(lambda: h.powerbase.command == mp.POWER_ON_TIMER_HALT, 'the halt')
            await asyncio.sleep(HALT_S)
            before_resume = len(h.records)

            await from_paho(ble.handle_race_control, {'command': 'resume'})
            await eventually(lambda: len(h.records) >= before_resume + 3, 'crossings after the resume')

    asyncio.run(scenario())
    assert_stamps_true(h)


def test_reconnect_while_paused_keeps_the_track_dead(harness):
    """Review item 2 end to end. Worst case for HW-07: the powerbase restores power when
    BLE drops. The connect-time write must follow the race (Paused -> halt), not put
    cars back on full power with marshals on the track."""
    h = harness
    h.powerbase.disconnect_power = 'on'

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.applied == [ble.POWER_ON_RACING], 'the connect-time power write')
            await from_paho(ble.handle_race_state, {'state': 'Running'})
            await eventually(lambda: len(h.records) >= 2, 'crossings while Running')
            await from_paho(ble.handle_race_state, {'state': 'Paused'})
            await eventually(lambda: h.powerbase.command == mp.POWER_ON_TIMER_HALT, 'the halt')
            writes_before_drop = len(h.applied)

            h.powerbase.on_disconnect()     # link lost, and the powerbase restores power
            assert h.powerbase.command == mp.POWER_ON_RACING

            await eventually(lambda: h.powerbase.connection_id == 2, 'the reconnect')
            await eventually(lambda: len(h.applied) > writes_before_drop, 'the connect-time write')
            assert h.applied[writes_before_drop:] == [ble.POWER_ON_TIMER_HALT]
            # Checked before teardown: cancelling run() disconnects cleanly, and with
            # disconnect_power='on' that restores power again.
            assert h.powerbase.command == mp.POWER_ON_TIMER_HALT

    asyncio.run(scenario())
    assert_stamps_true(h)   # cars ran while disconnected: seeding must hide those laps


def test_failed_halt_is_retried_until_the_track_is_dead(harness, monkeypatch):
    """A rejected POWER_ON_TIMER_HALT must not leave cars powered until the next race_state
    transition."""
    h = harness
    monkeypatch.setattr(ble, 'POWER_RETRY_INITIAL_DELAY', 0.2)
    h.faults.write_fail_rate = 1.0

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.faults.write_failures >= 1, 'the failed connect-time write')
            failures = h.faults.write_failures
            await from_paho(ble.handle_race_state, {'state': 'Paused'})
            await eventually(lambda: h.faults.write_failures > failures, 'the failed halt write')
            assert h.applied == []

            h.faults.write_fail_rate = 0.0
            await eventually(lambda: h.applied == [ble.POWER_ON_TIMER_HALT], 'the retried halt')
            await eventually(lambda: ble._power_retry_at is None, 'the retry to clear')

    asyncio.run(scenario())
    assert h.powerbase.command == mp.POWER_ON_TIMER_HALT


def test_retry_writes_the_current_race_state_not_the_failed_command(harness, monkeypatch):
    """The halt fails, then the race moves on to a state with no power write of its own
    (Finished). The retry must write what the race calls for now, full power, rather than
    replaying the stale halt."""
    h = harness
    monkeypatch.setattr(ble, 'POWER_RETRY_INITIAL_DELAY', 0.2)
    h.faults.write_fail_rate = 1.0

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.faults.write_failures >= 1, 'the failed connect-time write')
            await from_paho(ble.handle_race_state, {'state': 'Running'})
            failures = h.faults.write_failures
            await from_paho(ble.handle_race_state, {'state': 'Paused'})
            await eventually(lambda: h.faults.write_failures > failures, 'the failed halt write')
            await from_paho(ble.handle_race_state, {'state': 'Finished'})

            h.faults.write_fail_rate = 0.0
            await eventually(lambda: h.applied, 'the retry')
            await asyncio.sleep(1.5)        # room for a stale halt to land, if one were queued

    asyncio.run(scenario())
    assert h.applied == [ble.POWER_ON_RACING]
    assert h.powerbase.command == mp.POWER_ON_RACING
