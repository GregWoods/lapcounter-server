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

_here = __import__('pathlib').Path(__file__).parent
sys.path.insert(0, str(_here))
# lapdata's half of the contract. These scenarios are only meaningful end to end: ble
# publishes counters and clock ids, and lap_clock is what turns them back into lap times.
# Testing ble alone would prove the messages are well-formed, not that the laps are right.
sys.path.insert(0, str(_here.parent / 'lapdata'))
import ble_to_timestamps as ble  # noqa: E402
import mock_bleak  # noqa: E402
import mock_powerbase as mp  # noqa: E402
from lap_clock import ClockAnchors, Crossing, TIMING_COUNTER, interval_s  # noqa: E402

QUICK_LAPS = mp.LapModel(min_lap_s=0.5, ability_range_s=0.2, lap_spread_s=0.1,
                         outlier_chance=0, lane_change_chance=0.3)
SLOT_INTERVAL_S = 0.01
STOPPAGE_S = 2.0
# A lap measured from counters can only differ from the simulator's truth by the rounding
# of each end to a whole device tick, i.e. one tick over the pair. Nothing else gets in:
# not MQTT latency, not the round-robin reporting delay, not Windows' ~15ms sleep
# granularity. That is the entire point of the counter contract, so the tolerance is
# tight on purpose — a regression that reintroduces arrival-time timing blows straight
# through it.
LAP_TOLERANCE_S = mp.TICK_S + 1e-6


@pytest.fixture
def harness(monkeypatch):
    # Every published message, in order, with the monotonic time lapdata would have
    # stamped on arrival. In-process, so this is if anything *more* prompt than the real
    # MQTT hop — which only makes the anchor better, never the counters.
    sent = []

    def record(topic, payload):
        sent.append((topic, json.loads(payload), time.monotonic()))

    monkeypatch.setattr(ble, 'mqtt_client', types.SimpleNamespace(publish=record))

    # Disconnected, never-connected module state, as at container start.
    monkeypatch.setattr(ble, '_last_start_finish', [[None, None] for _ in range(6)])
    monkeypatch.setattr(ble, '_baseline_clock', [None] * 6)
    monkeypatch.setattr(ble, '_last_heartbeat_at', None)
    monkeypatch.setattr(ble, 'clock_heartbeat', 'throttle')
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
        # Byte 0 alone no longer says what a write did: racing and stopped are both
        # command 3, told apart only by the per-car multiplier in bytes 1-6.
        applied.append(ble.PowerState(payload[0], payload[1]))

    powerbase.apply_command = recording_apply
    faults = mock_bleak.Faults()
    mock_bleak.configure(powerbase, faults=faults, slot_interval_s=SLOT_INTERVAL_S)

    return types.SimpleNamespace(powerbase=powerbase, faults=faults, applied=applied, sent=sent)


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


def crossings_seen(h):
    return [p for topic, p, _ in h.sent if topic == ble.MQTT_TIMESTAMP_TOPIC]


def replay_through_lapdata(h):
    """What lapdata does with ble's output: feed every (clock, counter) sample to the
    anchors in arrival order, and collect each car+lane's crossings as Crossings.

    Deliberately the real lap_clock, not a reimplementation — the contract only means
    something if both halves agree on it.
    """
    anchors = ClockAnchors()
    per_lane = {}
    for topic, payload, arrival in h.sent:
        if topic not in (ble.MQTT_TIMESTAMP_TOPIC, ble.MQTT_CLOCK_TOPIC):
            continue
        anchors.observe(payload['clock'], payload['counter_ms'], arrival)
        if topic == ble.MQTT_TIMESTAMP_TOPIC:
            crossing = Crossing(payload['clock'], payload['counter_ms'], arrival)
            per_lane.setdefault((payload['car'], payload['lane']), []).append(crossing)
    return anchors, per_lane


def assert_no_phantom_laps(h):
    """A published crossing the simulator never made is a fabricated lap — the failure
    that seeding, and the per-car baseline clock, exist to prevent."""
    truth = {(car, lane, ticks) for car, lane, _at, ticks in h.powerbase.crossings}
    for topic, payload, _arrival in h.sent:
        if topic != ble.MQTT_TIMESTAMP_TOPIC:
            continue
        ticks = round(payload['counter_ms'] / 1000 / mp.TICK_S)
        assert (payload['car'], payload['lane'], ticks) in truth, (
            f"Phantom lap: car {payload['car']} lane {payload['lane']} at "
            f"{payload['counter_ms']}ms never crossed since connecting")


def assert_lap_times_true(h, minimum_laps=2):
    """Every lap lapdata would compute, against when the cars really crossed.

    Only consecutive crossings on the same clock, which is lap 2 onwards of any stretch
    of uninterrupted racing — exactly the laps the contract promises to get exactly
    right. A lap spanning a clock change goes through the anchor instead and is checked
    separately, where it matters.
    """
    anchors, per_lane = replay_through_lapdata(h)
    truth = {(car, lane, ticks): at for car, lane, at, ticks in h.powerbase.crossings}

    errors, counted = [], 0
    for (car, lane), crossings in per_lane.items():
        for before, after in zip(crossings, crossings[1:]):
            if before.clock != after.clock:
                continue
            measured, timing = interval_s(before, after, anchors)
            assert timing == 'counter', f'lap measured as {timing}, not an exact counter delta'
            key = lambda c: (car, lane, round(c.counter_ms / 1000 / mp.TICK_S))  # noqa: E731
            actual = truth[key(after)] - truth[key(before)]
            counted += 1
            if abs(measured - actual) > LAP_TOLERANCE_S:
                errors.append(f'car {car} lane {lane}: measured {measured:.3f}s, '
                              f'actually {actual:.3f}s')

    assert counted >= minimum_laps, f'only {counted} laps to check'
    assert not errors, f'{len(errors)} of {counted} laps wrong: {errors}'


def clocks_seen(h):
    return list(dict.fromkeys(p['clock'] for _t, p, _a in h.sent if 'clock' in p))


def assert_clocks_changed(h, at_least: int):
    """⚠️ Missing a clock change is now the thing that can go wrong: lapdata would
    subtract counters across a discontinuity and believe the answer."""
    distinct = len(clocks_seen(h))
    assert distinct >= at_least + 1, f'expected at least {at_least} clock changes, saw {distinct - 1}'


def cars_racing(h) -> bool:
    return h.powerbase.command == mp.POWER_ON_RACING and all(
        m & mp.MAX_POWER for m in h.powerbase.multipliers)


def cars_stopped(h) -> bool:
    """Held still by a zero power multiplier, with the powerbase still in POWER_ON_RACING
    so its timestamps keep ticking. Note the track stays energised — this stops the cars,
    it does not kill the track."""
    return h.powerbase.command == mp.POWER_ON_RACING and not any(
        m & mp.MAX_POWER for m in h.powerbase.multipliers)


def assert_one_lap_contains_the_stopped_time(h):
    """The lap either side of a stoppage is one long lap, measured exactly.

    ⚠️ This is the whole reason a stoppage is a zero multiplier and not command 4 (Greg,
    2026-09-20): the counter runs throughout, so the lap is still a plain counter
    subtraction rather than something converted through lapdata's anchors, and the stopped
    time is simply in it — as it should be. Cars stood still for two seconds of that lap.
    """
    anchors, per_lane = replay_through_lapdata(h)
    laps = [interval_s(before, after, anchors)
            for crossings in per_lane.values()
            for before, after in zip(crossings, crossings[1:])]
    assert laps, 'no laps to check'
    downgraded = [timing for _m, timing in laps if timing != TIMING_COUNTER]
    assert not downgraded, f'a stoppage must not downgrade any lap: {downgraded}'
    assert any(measured > STOPPAGE_S for measured, _t in laps), (
        f'no lap contains the {STOPPAGE_S}s the cars spent stopped: '
        f'{sorted(round(m, 2) for m, _t in laps)}')


# ------------------------------------------------------------------ scenarios

def test_lap_times_stay_true_across_a_stoppage(harness):
    """Review item 1 end to end: a yellow flag's power cut (or a manual pause) stops the
    cars WITHOUT stopping the powerbase's counter, so nothing about the stoppage reaches a
    lap time except the seconds the cars genuinely spent stationary.

    The powerbase starts with retained timestamps, so this also proves seeding on connect.
    """
    h = harness

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.applied == [ble.TRACK_RACING], 'the connect-time power write')
            # Several laps per car, not just one each: a single crossing per car gives
            # nothing to subtract, and the laps either side of the stoppage are the point.
            await eventually(lambda: len(crossings_seen(h)) >= 9, 'laps before the stoppage')

            await from_paho(ble.handle_race_control, {'command': 'pause'})
            await eventually(lambda: cars_stopped(h), 'the cars to stop')

            # Let the Slot round-robin drain, then check nothing crosses while the cars
            # stand still. The counter keeps running throughout, so a car still creeping
            # would show up here as a crossing.
            await asyncio.sleep(STOPPAGE_S / 2)
            stopped_count = len(crossings_seen(h))
            await asyncio.sleep(STOPPAGE_S / 2)
            assert len(crossings_seen(h)) == stopped_count, 'a car crossed while stopped'

            await from_paho(ble.handle_race_control, {'command': 'resume'})
            await eventually(lambda: cars_racing(h), 'the cars to race again')
            await eventually(lambda: len(crossings_seen(h)) >= stopped_count + 9,
                             'laps after the resume')

    asyncio.run(scenario())
    assert_no_phantom_laps(h)
    assert_lap_times_true(h)
    # ⚠️ The counter never stopped, so there is nothing for a new clock to be needed
    # FOR. A clock change here would mean a stoppage had broken the counter again.
    assert len(clocks_seen(h)) == 1, f'the stoppage changed clock: {clocks_seen(h)}'
    assert_one_lap_contains_the_stopped_time(h)


def test_reconnect_while_paused_keeps_the_cars_stopped(harness):
    """Review item 2 end to end. Worst case for HW-07: the powerbase restores power when
    BLE drops. The connect-time write must follow the race (Paused -> cars stopped), not
    set them moving again with marshals on the track."""
    h = harness
    h.powerbase.disconnect_power = 'on'

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.applied == [ble.TRACK_RACING], 'the connect-time power write')
            await from_paho(ble.handle_race_state, {'state': 'Running'})
            await eventually(lambda: len(crossings_seen(h)) >= 9, 'laps while Running')
            await from_paho(ble.handle_race_state, {'state': 'Paused'})
            await eventually(lambda: cars_stopped(h), 'the cars to stop')
            writes_before_drop = len(h.applied)

            clock_before_drop = ble._clock
            h.powerbase.on_disconnect()     # link lost, and the powerbase restores power
            assert cars_racing(h)

            await eventually(lambda: h.powerbase.connection_id == 2, 'the reconnect')
            # A reconnect always starts a new clock: the powerbase may have been
            # power-cycled while we were away, and we have no way to tell.
            assert ble._clock != clock_before_drop
            await eventually(lambda: len(h.applied) > writes_before_drop, 'the connect-time write')
            assert h.applied[writes_before_drop:] == [ble.CARS_STOPPED]
            # Checked before teardown: cancelling run() disconnects cleanly, and with
            # disconnect_power='on' that restores power again.
            assert cars_stopped(h)

    asyncio.run(scenario())
    # Cars ran while disconnected: seeding must hide those laps. (The new clock is
    # asserted inside the scenario — the cars stay stopped after the reconnect, so
    # nothing is ever published on it.)
    assert_no_phantom_laps(h)
    assert_lap_times_true(h)


def test_a_lap_completed_while_the_link_was_down_is_still_counted(harness, monkeypatch):
    """⚠️ Greg, 2026-09-20: "those crossings are real laps". The powerbase keeps racing while
    nothing is connected and remembers each car's last crossing, so a lap completed during a
    BLE drop is still there on reconnect. Clearing the per-car baselines on connect used to
    swallow it as a fresh seed — which is how a power cycle mid-race lost two laps.

    The reconnect is slowed here so the gap is long enough to contain a real lap; on the Pi
    it is chased as fast as possible for exactly this reason.
    """
    h = harness
    h.powerbase.disconnect_power = 'on'          # cars keep racing while we are away
    monkeypatch.setattr(ble, 'RECONNECT_FAST_DELAY', 1.2)

    async def scenario():
        async with ble_running():
            await eventually(lambda: len(crossings_seen(h)) >= 6, 'laps before the drop')
            dropped_at = time.time()
            h.powerbase.on_disconnect()
            await eventually(lambda: h.powerbase.connection_id == 2, 'the reconnect', timeout=10)
            reconnected_at = time.time()
            before = len(crossings_seen(h))
            await eventually(lambda: len(crossings_seen(h)) >= before + 3, 'laps after')
            return dropped_at, reconnected_at

    dropped_at, reconnected_at = asyncio.run(scenario())

    # Every crossing the simulator made while nobody was listening...
    in_the_gap = {(car, lane, ticks) for car, lane, at, ticks in h.powerbase.crossings
                  if dropped_at < at < reconnected_at}
    assert in_the_gap, 'no car crossed during the drop, so this proves nothing'

    published = {(p['car'], p['lane'], round(p['counter_ms'] / 1000 / mp.TICK_S))
                 for p in crossings_seen(h)}
    # ...and at least one of them must have come through. Only the most recent stamp per
    # car survives in the powerbase, so a car that crossed twice in the gap still loses one.
    assert published & in_the_gap, (
        f'every crossing during the drop was lost: {sorted(in_the_gap)}')

    assert_no_phantom_laps(h)
    assert_lap_times_true(h)


def test_a_power_cycle_is_a_new_clock_with_no_phantom_laps(harness):
    """The powerbase is switched off and on mid-race: it drops the link and zeroes its
    timers. Both halves of the trap are here — six cars' retained timestamps must not
    become six phantom laps on reconnect, and counters from before the power cycle must
    not be subtracted from counters after it."""
    h = harness

    async def scenario():
        async with ble_running():
            await eventually(lambda: len(crossings_seen(h)) >= 9, 'laps before the power cycle')
            before = len(crossings_seen(h))

            h.powerbase.power_cycle()

            await eventually(lambda: h.powerbase.connection_id == 2, 'the reconnect')
            await eventually(lambda: len(crossings_seen(h)) >= before + 9, 'laps after the power cycle')

    asyncio.run(scenario())
    assert_no_phantom_laps(h)
    assert_lap_times_true(h)
    assert_clocks_changed(h, at_least=1)


def test_failed_stop_is_retried_until_the_cars_stop(harness, monkeypatch):
    """A rejected CARS_STOPPED must not leave the cars racing until the next race_state
    transition."""
    h = harness
    monkeypatch.setattr(ble, 'POWER_RETRY_INITIAL_DELAY', 0.2)
    h.faults.write_fail_rate = 1.0

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.faults.write_failures >= 1, 'the failed connect-time write')
            failures = h.faults.write_failures
            await from_paho(ble.handle_race_state, {'state': 'Paused'})
            await eventually(lambda: h.faults.write_failures > failures, 'the failed stop write')
            assert h.applied == []

            h.faults.write_fail_rate = 0.0
            await eventually(lambda: h.applied == [ble.CARS_STOPPED], 'the retried stop')
            await eventually(lambda: ble._power_retry_at is None, 'the retry to clear')

    asyncio.run(scenario())
    assert cars_stopped(h)


def test_retry_writes_the_current_race_state_not_the_failed_command(harness, monkeypatch):
    """The stop fails, then the race moves on to a state with no power write of its own
    (Finished). The retry must write what the race calls for now, full power, rather than
    replaying the stale stop."""
    h = harness
    monkeypatch.setattr(ble, 'POWER_RETRY_INITIAL_DELAY', 0.2)
    h.faults.write_fail_rate = 1.0

    async def scenario():
        async with ble_running():
            await eventually(lambda: h.faults.write_failures >= 1, 'the failed connect-time write')
            await from_paho(ble.handle_race_state, {'state': 'Running'})
            failures = h.faults.write_failures
            await from_paho(ble.handle_race_state, {'state': 'Paused'})
            await eventually(lambda: h.faults.write_failures > failures, 'the failed stop write')
            await from_paho(ble.handle_race_state, {'state': 'Finished'})

            h.faults.write_fail_rate = 0.0
            await eventually(lambda: h.applied, 'the retry')
            await asyncio.sleep(1.5)        # room for a stale stop to land, if one were queued

    asyncio.run(scenario())
    assert h.applied == [ble.TRACK_RACING]
    assert cars_racing(h)
