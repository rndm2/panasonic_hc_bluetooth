import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak.exc import BleakError
from conftest import notify, status_packet

from custom_components.panasonic_hc.panasonic_hc import PanasonicHCException


async def test_disconnected_is_safe(thermostat):
    assert not thermostat.is_connected
    await thermostat.async_disconnect()
    await thermostat.async_disconnect()
    with pytest.raises(PanasonicHCException):
        await thermostat.async_set_power(True)


async def test_setup_requires_status(thermostat, connected):
    connected.write_gatt_char.side_effect = None
    with (
        patch(
            "custom_components.panasonic_hc.panasonic_hc.establish_connection",
            AsyncMock(return_value=connected),
        ),
        patch("custom_components.panasonic_hc.panasonic_hc.RESPONSE_TIMEOUT", 0.001),
    ):
        with pytest.raises(PanasonicHCException):
            await thermostat.async_connect()
    connected.disconnect.assert_awaited_once()
    assert not thermostat.available


async def test_notification_failure_cleans_connection(thermostat, connected):
    connected.start_notify.side_effect = BleakError("broken")
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        with pytest.raises(PanasonicHCException):
            await thermostat.async_connect()
    connected.disconnect.assert_awaited_once()


async def test_successful_connect(thermostat, connected):
    route = Mock(return_value=thermostat.device)
    thermostat._device_callback = route
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        await thermostat.async_connect()
    assert thermostat.available
    route.assert_called_once()


def test_invalid_packet_does_not_destroy_status(thermostat, connected):
    old = thermostat.status
    notify(thermostat, b"")
    assert thermostat.status is old
    assert thermostat.parse_errors == 1


def test_initial_missing_powersave(thermostat):
    notify(thermostat, status_packet(short=True))
    assert thermostat.status.powersave is None


def test_optional_powersave_preserved(thermostat):
    notify(thermostat, status_packet(eco=1))
    notify(thermostat, status_packet(short=True))
    assert thermostat.status.powersave is True


async def test_unconfirmed_command_raises(thermostat, connected):
    with pytest.raises(PanasonicHCException, match="confirm"):
        await thermostat.async_set_temperature(23)
    assert thermostat.status.settemp == 22


async def test_confirmed_command(thermostat, connected):
    await thermostat.async_set_temperature(22)
    assert connected.write_gatt_char.await_count == 2


async def test_invalid_mode_sends_nothing(thermostat, connected):
    with pytest.raises(ValueError):
        await thermostat.async_set_mode("bogus")
    connected.write_gatt_char.assert_not_awaited()


async def test_cancelled_connect_cleans_up(thermostat, connected):
    connected.start_notify.side_effect = asyncio.CancelledError
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        with pytest.raises(asyncio.CancelledError):
            await thermostat.async_connect()
    connected.disconnect.assert_awaited_once()


def test_disconnect_immediately_unavailable(thermostat, connected):
    listener = Mock()
    thermostat.register_update_callback(listener)
    thermostat._disconnected(connected)
    assert not thermostat.available
    listener.assert_called_once()


def test_resolve_device_refreshes_ha_lookup(thermostat, device):
    from bleak.backends.device import BLEDevice

    new_route = BLEDevice(device.address, device.name, {"source": "new-proxy"})
    thermostat._device_callback = Mock(side_effect=[device, new_route, None])
    assert thermostat._resolve_device() is device
    assert thermostat._resolve_device() is new_route
    with pytest.raises(BleakError, match="No connectable"):
        thermostat._resolve_device()


async def test_no_energy_requests(thermostat, connected):
    from custom_components.panasonic_hc.panasonic_hc_proto import _decode

    await thermostat.async_get_status()
    assert connected.write_gatt_char.await_count == 1
    assert _decode(connected.write_gatt_char.call_args.args[1])[5] == 129


async def test_disconnect_wakes_polling(thermostat, connected):
    thermostat.disconnected_event.clear()
    thermostat._disconnected(connected)
    assert thermostat.disconnected_event.is_set()


async def test_backend_cleanup_assertion_preserves_retryable_setup_error(thermostat, connected):
    connected.start_notify.side_effect = BleakError("Not connected")
    connected.disconnect.side_effect = AssertionError("services not cleared")
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        with pytest.raises(PanasonicHCException, match="initialize") as exc:
            await thermostat.async_connect()
    assert isinstance(exc.value.__cause__, BleakError)
    assert not thermostat.available
    assert thermostat._conn is None


async def test_cleanup_assertion_preserves_cancellation(thermostat, connected):
    connected.start_notify.side_effect = asyncio.CancelledError
    connected.disconnect.side_effect = AssertionError("services not cleared")
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        with pytest.raises(asyncio.CancelledError):
            await thermostat.async_connect()
    assert thermostat._conn is None


async def test_queued_notification_from_old_connection_is_ignored(thermostat, connected):
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        await thermostat.async_connect()
    callback = connected.start_notify.call_args.args[1]
    await thermostat.async_disconnect()
    old_status = thermostat.status
    callback(Mock(), bytearray(status_packet(temp=27)))
    assert thermostat.status is old_status
    assert not thermostat.ready


async def test_unexpected_setup_error_still_disconnects(thermostat, connected):
    connected.start_notify.side_effect = RuntimeError("backend failure")
    with patch(
        "custom_components.panasonic_hc.panasonic_hc.establish_connection",
        AsyncMock(return_value=connected),
    ):
        with pytest.raises(RuntimeError, match="backend failure"):
            await thermostat.async_connect()
    connected.disconnect.assert_awaited_once()
    assert thermostat._conn is None


async def test_delayed_command_confirmation_does_not_resend_command(thermostat, connected):
    from custom_components.panasonic_hc.panasonic_hc_proto import _decode

    requests = 0
    writes = []

    async def write(uuid, data):
        nonlocal requests
        ptype = _decode(data)[5]
        writes.append(ptype)
        if ptype == 129:
            requests += 1
            notify(thermostat, status_packet(temp=22 if requests == 1 else 25))

    connected.write_gatt_char.side_effect = write
    await thermostat.async_set_temperature(25)
    assert thermostat.status.settemp == 25
    assert writes == [76, 129, 129]
