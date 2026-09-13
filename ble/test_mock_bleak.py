"""Tests for the fake bleak surface behind the dev mocked-ble Layer 1.

Scenario tests running the real ble.run() against these fakes are step 4 of
docs/mocked-ble-plan.md; these only pin down the fakes themselves.
"""
import asyncio
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
import mock_bleak  # noqa: E402
import mock_powerbase as mp  # noqa: E402


@pytest.fixture
def powerbase():
    pb = mp.SimulatedPowerbase(cars=6, rng=random.Random(2))
    mock_bleak.configure(pb, slot_interval_s=0.001)
    return pb


def racing_payload():
    return bytes([mp.POWER_ON_RACING]) + bytes([mp.MAX_POWER] * 6) + bytes(13)


def test_scanner_finds_the_powerbase_with_the_real_name_filter(powerbase):
    """The advertised name has two trailing spaces; ble's filter must still match it."""
    device = asyncio.run(mock_bleak.FakeBleakScanner.find_device_by_filter(ble._name_matches, timeout=0))
    assert device.address == mock_bleak.MOCK_ADDRESS


def test_slot_notifications_reach_the_callback_and_decode(powerbase):
    received = []

    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS) as client:
            await client.start_notify(mock_bleak.SLOT_CHARACTERISTIC_UUID, lambda _s, data: received.append(data))
            # Poll rather than sleep a fixed time: Windows' timer resolution is ~15ms.
            for _ in range(500):
                if len(received) >= 12:
                    break
                await asyncio.sleep(0.01)
        assert not client.is_connected
        assert not powerbase.connected

    asyncio.run(scenario())
    assert len(received) >= 12
    assert {ble.decode_slot(p)[0] for p in received} == {1, 2, 3, 4, 5, 6}


def test_command_write_reaches_the_powerbase(powerbase):
    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS) as client:
            await client.write_gatt_char(mock_bleak.COMMAND_CHARACTERISTIC_UUID,
                                         ble.command_payload(ble.POWER_ON_TIMER_HALT))

    asyncio.run(scenario())
    assert powerbase.command == mp.POWER_ON_TIMER_HALT


def test_second_simultaneous_connection_is_refused(powerbase):
    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS):
            with pytest.raises(mock_bleak.FakeBleakError):
                await mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS).connect()

    asyncio.run(scenario())


def test_power_cycle_drops_the_client(powerbase):
    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS) as client:
            powerbase.power_cycle()
            assert not client.is_connected

    asyncio.run(scenario())


@pytest.mark.parametrize('faults', [
    mock_bleak.Faults(write_fail_rate=1.0),
    mock_bleak.Faults(no_command_characteristic=True),
])
def test_injected_write_faults_raise_and_leave_the_powerbase_alone(powerbase, faults):
    mock_bleak.configure(powerbase, faults=faults)

    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS) as client:
            with pytest.raises(mock_bleak.FakeBleakError):
                await client.write_gatt_char(mock_bleak.COMMAND_CHARACTERISTIC_UUID,
                                             bytes([mp.POWER_ON_TIMER_HALT]) + bytes(19))

    asyncio.run(scenario())
    assert powerbase.command == mp.POWER_ON_RACING


def test_rejected_payload_surfaces_as_a_gatt_error(powerbase):
    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS) as client:
            with pytest.raises(mock_bleak.FakeBleakError):
                await client.write_gatt_char(mock_bleak.COMMAND_CHARACTERISTIC_UUID, racing_payload()[:10])

    asyncio.run(scenario())


def test_injected_drop_disconnects_and_applies_disconnect_power(powerbase):
    powerbase.disconnect_power = 'off'
    mock_bleak.configure(powerbase, faults=mock_bleak.Faults(drop_every_s=0.01), slot_interval_s=0.001)

    async def scenario():
        async with mock_bleak.FakeBleakClient(mock_bleak.MOCK_ADDRESS) as client:
            for _ in range(500):
                if not client.is_connected:
                    break
                await asyncio.sleep(0.01)
            assert not client.is_connected

    asyncio.run(scenario())
    assert not powerbase.connected
    assert powerbase.command == mp.POWER_ON_TIMER_HALT
