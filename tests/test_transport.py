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
    await thermostat.async_disconnect()


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


async def test_command_deadline_with_no_status_marks_unavailable(thermostat, connected):
    connected.write_gatt_char.side_effect = None
    thermostat.disconnected_event.clear()
    with pytest.raises(PanasonicHCException, match="confirm"):
        await thermostat.async_set_temperature(25)
    assert not thermostat.available
    assert thermostat.disconnected_event.is_set()


def test_partial_status_preserves_current_temperature(thermostat):
    from conftest import parcel

    notify(thermostat, status_packet(current=24.5))
    notify(thermostat, parcel(bytes([65, 64, 0, 0, 120])))
    assert thermostat.status.curtemp == 24.5
    assert thermostat.status.settemp == 25


def test_repeated_ambiguous_temperature_does_not_bypass_filter(thermostat):
    notify(thermostat, status_packet(current=24.5))
    for _ in range(3):
        notify(thermostat, status_packet(current=-35))
        assert thermostat.current_temperature == 24.5
    notify(thermostat, status_packet(current=25))
    assert thermostat.current_temperature == 25


def test_partial_packets_do_not_renew_temperature_freshness(thermostat):
    from conftest import parcel

    clock = "custom_components.panasonic_hc.panasonic_hc.monotonic"
    with patch(clock, return_value=100):
        notify(thermostat, status_packet(current=24.5))
    with patch(clock, return_value=699):
        notify(thermostat, parcel(bytes([65, 64, 0, 0, 120])))
        assert thermostat.current_temperature == 24.5
    with patch(clock, return_value=700):
        notify(thermostat, parcel(bytes([65, 64, 0, 0, 120])))
        assert thermostat.current_temperature is None
        assert thermostat.status.curtemp is None
        assert thermostat._last_temperature == 24.5


async def test_temperature_expiry_publishes_without_new_packets(thermostat):
    thermostat._loop = asyncio.get_running_loop()
    changed = asyncio.Event()
    thermostat.register_update_callback(changed.set)
    with patch("custom_components.panasonic_hc.panasonic_hc.CURRENT_TEMPERATURE_MAX_AGE", 0.01):
        notify(thermostat, status_packet())
        changed.clear()
        await asyncio.wait_for(changed.wait(), timeout=1)
        assert thermostat.current_temperature is None
        assert thermostat.status.curtemp is None
        assert thermostat._temperature_expiry is None


async def test_disconnect_cancels_temperature_expiry(thermostat, connected):
    thermostat._loop = asyncio.get_running_loop()
    notify(thermostat, status_packet())
    timer = thermostat._temperature_expiry
    await thermostat.async_disconnect()
    assert timer.cancelled()
    assert thermostat.current_temperature is None


async def test_combined_temperature_and_mode_validated_before_writes(thermostat, connected):
    with pytest.raises(ValueError):
        await thermostat.async_set_temperature(12, "heat")
    with pytest.raises(ValueError):
        await thermostat.async_set_temperature(22, "bogus")
    connected.write_gatt_char.assert_not_awaited()


async def test_combined_temperature_and_mode_confirmation(thermostat, connected):
    from custom_components.panasonic_hc.panasonic_hc_proto import _decode

    async def write(uuid, data):
        if _decode(data)[5] == 129:
            notify(thermostat, status_packet(mode=1, temp=25))

    connected.write_gatt_char.side_effect = write
    await thermostat.async_set_temperature(25, "heat")
    assert thermostat.status.mode == "heat"
    assert thermostat.status.settemp == 25
    assert [_decode(c.args[1])[5] for c in connected.write_gatt_char.call_args_list] == [
        65,
        66,
        76,
        129,
    ]


async def test_busy_command_queue_is_bounded_without_writes(thermostat, connected):
    await thermostat._lock.acquire()
    try:
        with patch("custom_components.panasonic_hc.panasonic_hc.COMMAND_QUEUE_TIMEOUT", 0.001):
            with pytest.raises(PanasonicHCException, match="still in progress"):
                await thermostat.async_set_temperature(22)
        connected.write_gatt_char.assert_not_awaited()
        assert thermostat._lock.locked()
    finally:
        thermostat._lock.release()
    await thermostat.async_set_temperature(22)


async def test_cancelled_queued_command_does_not_unlock_another_operation(thermostat, connected):
    await thermostat._lock.acquire()
    task = asyncio.create_task(thermostat.async_set_temperature(22))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert thermostat._lock.locked()
    connected.write_gatt_char.assert_not_awaited()
    thermostat._lock.release()


async def test_combined_off_and_temperature(thermostat, connected):
    from custom_components.panasonic_hc.panasonic_hc_proto import _decode

    async def write(uuid, data):
        if _decode(data)[5] == 129:
            notify(thermostat, status_packet(power=False, temp=25))

    connected.write_gatt_char.side_effect = write
    await thermostat.async_set_temperature(25, "off")
    assert not thermostat.status.power
    assert thermostat.status.settemp == 25
    assert [_decode(c.args[1])[5] for c in connected.write_gatt_char.call_args_list] == [
        76,
        65,
        129,
    ]
