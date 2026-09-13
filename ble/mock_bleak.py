"""Fake bleak surface in front of mock_powerbase.SimulatedPowerbase, so the real
ble_to_timestamps.run() can talk to a simulated powerbase. See docs/mocked-ble-plan.md.

Only the parts of bleak that ble_to_timestamps.py uses: BleakScanner.find_device_by_filter
and a BleakClient that is an async context manager with is_connected, start_notify and
write_gatt_char. Everything runs on the caller's event loop, and notification callbacks
fire on that loop's thread, the same as real bleak.

configure() must be called before the first connect; it's the one powerbase every client
talks to, since the simulated device outlives any single connection.
"""
import asyncio
import dataclasses
import logging
import random
import types

from mock_powerbase import SimulatedPowerbase

logger = logging.getLogger(__name__)

# The powerbase's GATT characteristics, per the protocol doc. Deliberately not imported
# from ble_to_timestamps: see mock_powerbase's module docstring.
SLOT_CHARACTERISTIC_UUID = '00003b0b-0000-1000-8000-00805f9b34fb'
COMMAND_CHARACTERISTIC_UUID = '00003b0a-0000-1000-8000-00805f9b34fb'

# Two trailing spaces, per the spec's Advertising Packet section, so _name_matches() is
# exercised rather than an exact match.
ADVERTISED_NAME = 'Scalextric ARC  '
MOCK_ADDRESS = '00:00:5E:00:53:A7'     # documentation-range MAC


class FakeBleakError(Exception):
    """Stands in for bleak.exc.BleakError."""


@dataclasses.dataclass
class Faults:
    drop_every_s: float | None = None      # disconnect this long after each connect
    write_fail_rate: float = 0.0           # chance that a Command write raises
    no_command_characteristic: bool = False  # ARC One: every Command write rejected
    rng: random.Random = dataclasses.field(default_factory=random.Random)
    write_failures: int = 0                # count of writes failed by the two faults above


_powerbase: SimulatedPowerbase | None = None
_faults = Faults()
_slot_interval_s = 0.05


def configure(powerbase: SimulatedPowerbase, faults: Faults | None = None, slot_interval_s: float = 0.05):
    global _powerbase, _faults, _slot_interval_s
    _powerbase = powerbase
    _faults = faults or Faults()
    _slot_interval_s = slot_interval_s


def _same_uuid(char_specifier, uuid: str) -> bool:
    return str(getattr(char_specifier, 'uuid', char_specifier)).lower() == uuid


class FakeBleakScanner:
    @staticmethod
    async def find_device_by_filter(filterfunc, timeout: float = 10.0, **_kwargs):
        device = types.SimpleNamespace(name=ADVERTISED_NAME, address=MOCK_ADDRESS)
        advertisement = types.SimpleNamespace(local_name=ADVERTISED_NAME)
        if filterfunc(device, advertisement):
            return device
        await asyncio.sleep(timeout)
        return None


class FakeBleakClient:
    def __init__(self, address_or_ble_device, **_kwargs):
        if _powerbase is None:
            raise RuntimeError('mock_bleak.configure() has not been called')
        self.address = getattr(address_or_ble_device, 'address', address_or_ble_device)
        self._connection_id: int | None = None
        self._tasks: list[asyncio.Task] = []

    @property
    def is_connected(self) -> bool:
        return (self._connection_id is not None
                and _powerbase.connected
                and _powerbase.connection_id == self._connection_id)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_exc):
        await self.disconnect()

    async def connect(self, **_kwargs):
        if self.address != MOCK_ADDRESS:
            raise FakeBleakError(f'Device with address {self.address} was not found')
        try:
            self._connection_id = _powerbase.on_connect()
        except ValueError as e:
            raise FakeBleakError(str(e)) from e
        if _faults.drop_every_s:
            self._tasks.append(asyncio.create_task(self._drop_after(_faults.drop_every_s)))
        return True

    async def disconnect(self):
        others = [t for t in self._tasks if t is not asyncio.current_task()]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        self._tasks.clear()
        self._lose_link()
        return True

    def _lose_link(self):
        if self.is_connected:
            _powerbase.on_disconnect()
        self._connection_id = None

    async def _drop_after(self, seconds: float):
        await asyncio.sleep(seconds)
        logger.warning(f'Injected BLE drop after {seconds}s')
        self._lose_link()

    async def start_notify(self, char_specifier, callback, **_kwargs):
        if not self.is_connected:
            raise FakeBleakError('Not connected')
        if not _same_uuid(char_specifier, SLOT_CHARACTERISTIC_UUID):
            raise FakeBleakError(f'Characteristic {char_specifier} does not support notify in this mock')
        self._tasks.append(asyncio.create_task(self._pump_slot(callback)))

    async def _pump_slot(self, callback):
        sender = types.SimpleNamespace(uuid=SLOT_CHARACTERISTIC_UUID)
        while self.is_connected:
            await asyncio.sleep(_slot_interval_s)
            if not self.is_connected:
                break
            try:
                callback(sender, bytearray(_powerbase.next_slot_packet()))
            except Exception:
                logger.exception('Slot notification callback raised')

    async def write_gatt_char(self, char_specifier, data, response: bool | None = None):
        if not self.is_connected:
            raise FakeBleakError('Not connected')
        if not _same_uuid(char_specifier, COMMAND_CHARACTERISTIC_UUID):
            raise FakeBleakError(f'Characteristic {char_specifier} is not writable in this mock')
        if _faults.no_command_characteristic:
            _faults.write_failures += 1
            raise FakeBleakError(f'Characteristic {char_specifier} was not found!')
        if _faults.rng.random() < _faults.write_fail_rate:
            _faults.write_failures += 1
            raise FakeBleakError('Injected Command write failure')
        try:
            _powerbase.apply_command(bytes(data))
        except ValueError as e:
            raise FakeBleakError(f'GATT write rejected: {e}') from e
