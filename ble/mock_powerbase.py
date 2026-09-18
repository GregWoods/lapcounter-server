"""Simulated Scalextric ARC Pro powerbase, so dev can run the real ble_to_timestamps.py
with no Bluetooth adapter and no track. See docs/mocked-ble-plan.md.

A pure simulation: no asyncio, no BLE, no MQTT, and an injectable clock so tests can run
it faster than real time. mock_bleak.py puts a fake bleak surface in front of it.

The simulation is lazy. Nothing ticks in the background; every public call first
advances the device to `clock()`, working out any crossings that happened in between at
the exact instant they happened. So a car that crossed while nobody was polling is
stamped correctly, and only its most recent crossing survives in StartFinish, which is
how the real Slot characteristic behaves too.

Protocol constants are defined here rather than imported from ble_to_timestamps. This is
the *device*: a simulator that shared the code-under-test's constants would agree with
a wrong one.

Every behaviour the hardware hasn't confirmed yet is tagged with the check in
ble/HARDWARE_VALIDATION.md that will settle it (e.g. `# HW-06`). When hw-report.json
comes back, grep for the tags and correct the simulation to match the hardware.
"""
import collections
import dataclasses
import logging
import random
import struct
import time

logger = logging.getLogger(__name__)

SLOT_IDS = 6                    # the Slot characteristic reports car IDs 1-6
COMMAND_PACKET_LENGTH = 20
MAX_POWER = 0x3F                # Command bytes 1-6: power multiplier 0...0x3f
UINT32_MASK = 0xFFFFFFFF
# The device clock counts 10ms ticks, not the milliseconds the protocol doc claims:
# measured on a real ARC Pro (HW-04, HW-10, HW-12, 2026-09-18). Deliberately its own
# constant, not ble_to_timestamps.DEVICE_TICK_S - see the module docstring.
TICK_S = 0.01

NO_POWER_TIMER_STOPPED = 0
NO_POWER_TIMER_TICKING = 1
POWER_ON_RACE_TRIGGER = 2
POWER_ON_RACING = 3
POWER_ON_TIMER_HALT = 4
NO_POWER_REBOOT_PIC18 = 5


@dataclasses.dataclass(frozen=True)
class _CommandBehaviour:
    track_power: bool
    timestamps_tick: bool
    zeroes_timestamps: bool
    cars_move: bool


# From the protocol doc's command table (ble/reference/Scalextric_ARC_BLE_Protocol.md).
_COMMANDS = {
    # "track power off and time stamps ... reset to 0"          HW-09: are they zeroed?
    NO_POWER_TIMER_STOPPED: _CommandBehaviour(False, False, True, False),
    # "power to track but all speed 0, time stamps zeroed". Named TICKING, so assumed
    # zeroed once on the write and ticking from there.                  HW-09 (unverified)
    NO_POWER_TIMER_TICKING: _CommandBehaviour(True, True, True, False),
    # "power to track, time stamps halt". Whether outputs still follow the throttle is
    # not documented, and ble never sends it, so cars are assumed stationary.
    POWER_ON_RACE_TRIGGER: _CommandBehaviour(True, False, False, False),
    # "time stamps ticking, power outputs follow the throttle levels and the car power
    # bytes".                                                                   HW-03
    POWER_ON_RACING: _CommandBehaviour(True, True, False, True),
    # "power off, but time stamps halt": the clock pauses, rather than ticking on or
    # resetting.                                                                HW-06
    POWER_ON_TIMER_HALT: _CommandBehaviour(False, False, False, False),
}

DISCONNECT_POWER_MODES = ('hold', 'off', 'on')


@dataclasses.dataclass(frozen=True)
class LapModel:
    """Borrowed from gpio/mocked_timestamps.py: base + per-car ability + per-lap spread,
    plus the occasional off. Times are at full power; a lower multiplier stretches them."""
    min_lap_s: float = 5.0
    ability_range_s: float = 4.2
    lap_spread_s: float = 3.5
    outlier_chance: float = 0.05
    outlier_extra_s: tuple[float, float] = (5.0, 13.0)
    lane_change_chance: float = 0.1

    def __post_init__(self):
        if self.min_lap_s <= 0:
            raise ValueError('min_lap_s must be > 0, or a car would cross infinitely often')


class SimulatedCar:
    def __init__(self, car_id: int, lane: int, lap_model: LapModel, rng: random.Random):
        self.car_id = car_id
        self.lane = lane
        self.base_lap_s = lap_model.min_lap_s + rng.uniform(0, lap_model.ability_range_s)
        self.spread_s = rng.uniform(0, lap_model.lap_spread_s)
        # Lap "distance" still to go, in seconds at full power. Starting somewhere round
        # the lap stops every car crossing in the same instant.
        self.remaining_s = rng.uniform(0, self.base_lap_s)
        self.laps = 0
        # Last StartFinish1/StartFinish2 stamps, device ticks (lane 1, lane 2).
        self.start_finish = [0, 0]


class SimulatedPowerbase:
    def __init__(self, cars: int = 6, *, clock=time.monotonic, rng: random.Random | None = None,
                 lap_model: LapModel | None = None, retained_timestamps: bool = True,
                 disconnect_power: str = 'hold'):
        if not 0 <= cars <= SLOT_IDS:
            raise ValueError(f'cars must be 0-{SLOT_IDS}, got {cars}')
        if disconnect_power not in DISCONNECT_POWER_MODES:
            raise ValueError(f'disconnect_power must be one of {DISCONNECT_POWER_MODES}')
        self._clock = clock
        self._rng = rng or random.Random()
        self.lap_model = lap_model or LapModel()
        # HW-07: what a BLE drop does to track power is unknown. 'hold' (keep whatever
        # was last written) is what ble_to_timestamps currently assumes.
        self.disconnect_power = disconnect_power

        self.connected = False
        self.connection_id = 0
        # HW-08: assumed to power the track before any app has connected, like a
        # standalone ARC Pro, and with every multiplier at full.
        self.command = POWER_ON_RACING
        self.multipliers = [MAX_POWER] * SLOT_IDS
        self._device_s = 0.0
        self._last_update = clock()
        self._sequence = 0
        self._next_slot_index = 0
        self._listeners = []
        # Ground truth for tests: (car, lane, clock() at the crossing, device ticks stamped).
        # (car, lane, device ticks) identifies a crossing, since stamps only move forward.
        self.crossings = collections.deque(maxlen=1000)
        self.cars = [SimulatedCar(i + 1, lane=1 + i % 2, lap_model=self.lap_model, rng=self._rng)
                     for i in range(cars)]
        if retained_timestamps:
            self._seed_retained_state()

    # ------------------------------------------------------------------ state

    @property
    def behaviour(self) -> _CommandBehaviour:
        return _COMMANDS[self.command]

    @property
    def device_ticks(self) -> int:
        self.advance()
        return round(self._device_s / TICK_S) & UINT32_MASK

    def add_listener(self, callback):
        """callback() after every command, connect, disconnect or power cycle. Crossings
        don't notify: they only happen inside advance(), which is lazy."""
        self._listeners.append(callback)

    def speed(self, car: SimulatedCar) -> float:
        """Fraction of full pace. Ignores the 0x80 direct-drive bit: there's no simulated
        throttle, so a driven car and a trigger-held-flat car are the same thing."""
        if not self.behaviour.cars_move:
            return 0.0
        return (self.multipliers[car.car_id - 1] & MAX_POWER) / MAX_POWER

    def snapshot(self) -> dict:
        """What mock/powerbase publishes. Dev-only observability, not part of any contract."""
        self.advance()
        return {
            'connected': self.connected,
            'command': self.command,
            'track_power': self.behaviour.track_power,
            'timestamps_ticking': self.behaviour.timestamps_tick,
            'device_ticks': self.device_ticks,
            'cars': [{'car': c.car_id, 'lane': c.lane, 'laps': c.laps, 'moving': self.speed(c) > 0}
                     for c in self.cars],
        }

    # --------------------------------------------------------------- simulation

    def advance(self):
        """Run the simulation forward to clock(), stamping any crossings in between at
        the device time they actually happened."""
        now = self._clock()
        dt = now - self._last_update
        if dt <= 0:
            return
        self._last_update = now
        start_clock = now - dt
        start_device_s = self._device_s
        ticking = self.behaviour.timestamps_tick

        for car in self.cars:
            speed = self.speed(car)
            if speed <= 0:
                continue
            elapsed = 0.0
            while car.remaining_s / speed <= dt - elapsed:
                elapsed += car.remaining_s / speed
                self._cross(car, start_device_s + elapsed if ticking else start_device_s,
                            start_clock + elapsed)
                car.remaining_s = self._next_lap_s(car)
            car.remaining_s -= (dt - elapsed) * speed

        if ticking:
            self._device_s += dt

    def _cross(self, car: SimulatedCar, device_s: float, at: float):
        stamp = round(device_s / TICK_S) & UINT32_MASK
        car.start_finish[car.lane - 1] = stamp
        car.laps += 1
        self.crossings.append((car.car_id, car.lane, at, stamp))
        logger.debug(f'car {car.car_id} crossed lane {car.lane} at device {device_s:.2f}s')
        if self._rng.random() < self.lap_model.lane_change_chance:
            car.lane = 3 - car.lane

    def _next_lap_s(self, car: SimulatedCar) -> float:
        lap = car.base_lap_s + self._rng.uniform(0, car.spread_s)
        if self._rng.random() < self.lap_model.outlier_chance:
            lap += self._rng.uniform(*self.lap_model.outlier_extra_s)
        return lap

    def _seed_retained_state(self):
        """HW-02: the powerbase hands over each car's last crossing on connect, so a fresh
        mock looks like one that's been raced on. Every connect then exercises seeding."""
        self._device_s = self._rng.uniform(60, 600)
        for car in self.cars:
            last = max(0.0, self._device_s - self._rng.uniform(0, 30))
            car.start_finish[car.lane - 1] = round(last / TICK_S)

    def _zero_timestamps(self):
        self._device_s = 0.0
        for car in self.cars:
            car.start_finish = [0, 0]

    def _changed(self):
        for callback in self._listeners:
            callback()

    # ----------------------------------------------------------------- BLE side

    def next_slot_packet(self) -> bytes:
        """The next 18-byte Slot notification: sequence, car ID, StartFinish1/2 (uint32 ticks,
        little-endian), then pitlane1/2, which this project never reads.

        HW-02: round-robin over all 6 car IDs whether or not a car is on the track, so the
        worst-case reporting delay is a full 6-packet cycle."""
        self.advance()
        car_id = self._next_slot_index + 1
        self._next_slot_index = (self._next_slot_index + 1) % SLOT_IDS
        car = next((c for c in self.cars if c.car_id == car_id), None)
        track1, track2 = car.start_finish if car else (0, 0)
        packet = struct.pack('<BBIIII', self._sequence, car_id, track1, track2, 0, 0)
        self._sequence = (self._sequence + 1) & 0xFF
        return packet

    def apply_command(self, payload: bytes):
        """A Command characteristic write. Raises ValueError for anything the device
        would reject; mock_bleak turns that into a failed GATT write."""
        if len(payload) != COMMAND_PACKET_LENGTH:
            raise ValueError(f'Command write must be {COMMAND_PACKET_LENGTH} bytes, got {len(payload)}')
        command = payload[0]
        if command == NO_POWER_REBOOT_PIC18:
            raise ValueError('Command 5 puts the PIC18 into DFU mode; the simulator refuses it')
        if command not in _COMMANDS:
            raise ValueError(f'Unknown command {command}')

        self.advance()
        multipliers = list(payload[1:7])
        if command == POWER_ON_RACING and not any(m & MAX_POWER for m in multipliers):
            logger.warning('POWER_ON_RACING with every power multiplier (bytes 1-6) at zero: '
                           'no car can move. Those bytes are multipliers, not padding.')
        self.command = command
        self.multipliers = multipliers
        if _COMMANDS[command].zeroes_timestamps:
            self._zero_timestamps()
        logger.info(f'Simulated powerbase <- command {command}')
        self._changed()

    def on_connect(self) -> int:
        """Returns an id for this connection. A client holding an older id has lost its
        link, even if it never saw the drop (e.g. across a power cycle)."""
        if self.connected:
            raise ValueError('The powerbase accepts one BLE connection at a time')
        self.advance()
        self.connected = True
        self.connection_id += 1
        self._changed()
        return self.connection_id

    def on_disconnect(self):
        self.advance()
        self.connected = False
        # HW-07
        if self.disconnect_power == 'off':
            self.command = POWER_ON_TIMER_HALT
        elif self.disconnect_power == 'on':
            self.command = POWER_ON_RACING
            self.multipliers = [MAX_POWER] * SLOT_IDS
        self._changed()

    def power_cycle(self):
        """Switch the powerbase off and on. HW-08: assumed to zero the timers and come
        back in its standalone, powered state. Drops any BLE connection."""
        self.advance()
        self.connected = False
        self.command = POWER_ON_RACING
        self.multipliers = [MAX_POWER] * SLOT_IDS
        self._zero_timestamps()
        logger.info('Simulated powerbase power-cycled')
        self._changed()
