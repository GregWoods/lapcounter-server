"""Tests for the simulated powerbase behind the dev mocked-ble Layer 1.

paho and bleak are stubbed before importing ble_to_timestamps, as in
test_ble_to_timestamps.py, so its real decode_slot() can check the simulated packets.
"""
import logging
import random
import sys
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
import mock_powerbase as mp  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def tick(self, seconds):
        self.now += seconds


# Every lap exactly 2s at full power, no lane changes: crossings land where the test says.
STEADY = mp.LapModel(min_lap_s=2.0, ability_range_s=0, lap_spread_s=0,
                     outlier_chance=0, lane_change_chance=0)


@pytest.fixture
def clock():
    return FakeClock()


def make_powerbase(clock, cars=1, **kwargs):
    kwargs.setdefault('lap_model', STEADY)
    kwargs.setdefault('retained_timestamps', False)
    return mp.SimulatedPowerbase(cars=cars, clock=clock, rng=random.Random(1), **kwargs)


def command(code, power=mp.MAX_POWER):
    return bytes([code]) + bytes([power] * 6) + bytes(13)


# ------------------------------------------------------------------ packets

def test_packets_round_trip_through_the_real_decoder(clock):
    pb = make_powerbase(clock, cars=2)
    pb.cars[0].start_finish = [12_345, 0]
    pb.cars[1].start_finish = [0, 67_890]

    packets = [pb.next_slot_packet() for _ in range(7)]

    assert all(len(p) == 18 for p in packets)
    assert ble.decode_slot(bytearray(packets[0])) == (1, 12_345, 0)
    assert ble.decode_slot(bytearray(packets[1])) == (2, 0, 67_890)


def test_slot_packets_round_robin_all_six_ids_with_a_sequence(clock):
    """HW-02: round-robin covers every ID, cars on track or not."""
    pb = make_powerbase(clock, cars=2)
    packets = [pb.next_slot_packet() for _ in range(8)]
    assert [p[1] for p in packets] == [1, 2, 3, 4, 5, 6, 1, 2]
    assert [p[0] for p in packets] == list(range(8))
    assert ble.decode_slot(bytearray(packets[3])) == (4, 0, 0)


# ---------------------------------------------------------------- crossings

def test_crossings_are_stamped_when_they_happen_not_when_polled(clock):
    pb = make_powerbase(clock)
    car = pb.cars[0]
    car.remaining_s = 1.0

    clock.tick(1.7)                 # crossed at 1.0s, nobody polled until 1.7s
    pb.advance()
    assert car.start_finish == [100, 0]
    assert car.laps == 1

    clock.tick(1.5)                 # next crossing 2s after the last, at 3.0s
    pb.advance()
    assert car.start_finish == [300, 0]


def test_several_crossings_in_one_step_keep_only_the_latest(clock):
    """Like the real Slot characteristic: an unpolled gap loses the earlier stamps."""
    pb = make_powerbase(clock)
    pb.cars[0].remaining_s = 1.0
    clock.tick(7.5)                 # crossings at 1, 3, 5, 7
    pb.advance()
    assert pb.cars[0].laps == 4
    assert pb.cars[0].start_finish == [700, 0]


def test_lane_change_stamps_the_other_start_finish_field(clock):
    pb = make_powerbase(clock, lap_model=mp.LapModel(min_lap_s=2.0, ability_range_s=0, lap_spread_s=0,
                                                     outlier_chance=0, lane_change_chance=1.0))
    pb.cars[0].remaining_s = 1.0
    clock.tick(3.5)                 # crossing at 1 on lane 1, then at 3 on lane 2
    pb.advance()
    assert pb.cars[0].start_finish == [100, 300]


def test_retained_timestamps_look_like_a_used_powerbase(clock):
    """So every connect exercises ble's seeding instead of starting from zero."""
    pb = mp.SimulatedPowerbase(cars=6, clock=clock, rng=random.Random(7))
    assert pb.device_ticks > 0
    for car in pb.cars:
        assert 0 < max(car.start_finish) <= pb.device_ticks


# ----------------------------------------------------------------- commands

def test_timer_halt_freezes_the_clock_and_stops_cars(clock):
    """HW-06: the device clock pauses through a halt, so a crossing after resume is
    stamped as if the halt never happened. This is what ble must re-anchor across."""
    pb = make_powerbase(clock)
    car = pb.cars[0]
    car.remaining_s = 5.0

    clock.tick(1.0)
    pb.apply_command(command(mp.POWER_ON_TIMER_HALT))
    assert pb.snapshot()['track_power'] is False

    clock.tick(10.0)
    assert pb.device_ticks == 100
    assert car.laps == 0

    pb.apply_command(command(mp.POWER_ON_RACING))
    clock.tick(4.5)                 # 4s of lap left at the halt
    pb.advance()
    assert car.start_finish == [500, 0]
    assert pb.device_ticks == 550


def test_command_0_zeroes_and_stops_the_timers(clock):
    """HW-09."""
    pb = mp.SimulatedPowerbase(cars=6, clock=clock, rng=random.Random(3), lap_model=STEADY)
    pb.apply_command(command(mp.NO_POWER_TIMER_STOPPED))
    assert all(car.start_finish == [0, 0] for car in pb.cars)
    clock.tick(5.0)
    assert pb.device_ticks == 0
    assert pb.snapshot()['track_power'] is False


def test_command_1_zeroes_then_ticks_with_cars_stationary(clock):
    pb = mp.SimulatedPowerbase(cars=2, clock=clock, rng=random.Random(3), lap_model=STEADY)
    pb.apply_command(command(mp.NO_POWER_TIMER_TICKING))
    clock.tick(5.0)
    assert pb.device_ticks == 500
    assert all(car.laps == 0 and car.start_finish == [0, 0] for car in pb.cars)


def test_zero_multiplier_bytes_stop_every_car(clock, caplog):
    """Bytes 1-6 are multipliers, not padding — and as of 2026-09-20 zeroing them is how
    ble stops the cars for a yellow flag or a pause (CARS_STOPPED), precisely BECAUSE the
    timestamps keep ticking through it: the lap either side of a stoppage stays an exact
    counter subtraction, with the stopped time in it."""
    pb = make_powerbase(clock)
    pb.cars[0].remaining_s = 1.0
    with caplog.at_level(logging.INFO, logger=mp.__name__):
        pb.apply_command(command(mp.POWER_ON_RACING, power=0))
    assert 'cars held stationary' in caplog.text

    clock.tick(10.0)
    pb.advance()
    assert pb.cars[0].laps == 0
    assert pb.device_ticks == 1_000       # clock still ticks, cars just can't move


def test_half_multiplier_halves_the_pace(clock):
    pb = make_powerbase(clock)
    pb.cars[0].remaining_s = 1.0
    pb.apply_command(command(mp.POWER_ON_RACING, power=mp.MAX_POWER // 2 + 1))  # 32/63
    clock.tick(1.9)
    pb.advance()
    assert pb.cars[0].laps == 0
    clock.tick(0.1)
    pb.advance()
    assert pb.cars[0].laps == 1


@pytest.mark.parametrize('payload', [
    command(mp.POWER_ON_RACING)[:19],               # short
    command(mp.NO_POWER_REBOOT_PIC18),              # DFU
    command(9),                                     # unknown
])
def test_invalid_writes_are_rejected_without_changing_state(clock, payload):
    pb = make_powerbase(clock)
    with pytest.raises(ValueError):
        pb.apply_command(payload)
    assert pb.command == mp.POWER_ON_RACING


def test_listeners_hear_commands(clock):
    pb = make_powerbase(clock)
    heard = []
    pb.add_listener(lambda: heard.append(pb.command))
    pb.apply_command(command(mp.POWER_ON_TIMER_HALT))
    assert heard == [mp.POWER_ON_TIMER_HALT]


# ------------------------------------------------- connection and power cycle

def test_one_connection_at_a_time(clock):
    pb = make_powerbase(clock)
    first = pb.on_connect()
    with pytest.raises(ValueError):
        pb.on_connect()
    pb.on_disconnect()
    assert pb.on_connect() == first + 1


@pytest.mark.parametrize('mode, expected', [
    ('hold', mp.POWER_ON_TIMER_HALT),
    ('off', mp.POWER_ON_TIMER_HALT),
    ('on', mp.POWER_ON_RACING),
])
def test_disconnect_power_mode_while_halted(clock, mode, expected):
    """HW-07: 'on' is the unsafe case, a BLE drop restoring power during a yellow flag."""
    pb = make_powerbase(clock, disconnect_power=mode)
    pb.on_connect()
    pb.apply_command(command(mp.POWER_ON_TIMER_HALT))
    pb.on_disconnect()
    assert pb.command == expected


def test_disconnect_off_while_racing_stops_cars(clock):
    pb = make_powerbase(clock, disconnect_power='off')
    pb.on_connect()
    pb.on_disconnect()
    assert pb.command == mp.POWER_ON_TIMER_HALT


def test_power_cycle_zeroes_timers_and_drops_the_connection(clock):
    """HW-08."""
    pb = mp.SimulatedPowerbase(cars=2, clock=clock, rng=random.Random(5), lap_model=STEADY)
    pb.on_connect()
    pb.apply_command(command(mp.POWER_ON_TIMER_HALT))
    pb.power_cycle()
    assert not pb.connected
    assert pb.command == mp.POWER_ON_RACING
    assert pb.device_ticks == 0
    assert all(car.start_finish == [0, 0] for car in pb.cars)
