"""Regressions for reconnecting without losing ownership of a live session."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak.exc import BleakError

from custom_components.panasonic_hc.errors import PanasonicHCException


async def test_failed_disconnect_retains_live_client(thermostat, connected):
    connected.disconnect.side_effect = TimeoutError("backend still closing")
    await thermostat.async_disconnect()
    assert thermostat.transport.client is connected
    assert thermostat.transport.stage == "disconnect_failed"


async def test_new_connect_cannot_overlap_failed_teardown(thermostat, connected):
    connected.disconnect.side_effect = TimeoutError("backend still closing")
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ) as establish:
        with pytest.raises(PanasonicHCException, match="previous BLE session"):
            await thermostat.transport.connect()
    establish.assert_not_awaited()
    assert thermostat.transport.client is connected


async def test_existing_bond_connect_does_not_start_new_pairing(thermostat, connected):
    thermostat.transport.client = None
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ):
        await thermostat.async_connect()
    assert thermostat.available
    connected.pair.assert_not_awaited()
    connected.unpair.assert_not_called()
    await thermostat.async_disconnect()


async def test_security_in_progress_retries_notify_on_same_session(thermostat, connected):
    started, authenticated = asyncio.Event(), asyncio.Event()

    async def subscribe(*args):
        if not authenticated.is_set():
            started.set()
            raise BleakError("Insufficient authentication")

    connected.start_notify.side_effect = subscribe
    thermostat.transport.client = None
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ) as establish:
        task = asyncio.create_task(thermostat.async_connect())
        await started.wait()
        assert thermostat.transport.stage == "authenticating"
        connected.disconnect.assert_not_awaited()
        connected.write_gatt_char.assert_not_awaited()
        connected.pair.assert_not_awaited()
        authenticated.set()
        await task
    assert thermostat.available
    assert establish.await_count == 1
    assert connected.start_notify.await_count >= 2
    await thermostat.async_disconnect()


async def test_security_wait_timeout_keeps_root_cause(thermostat, connected):
    from custom_components.panasonic_hc.errors import PanasonicAuthenticationError

    connected.start_notify.side_effect = BleakError("Insufficient encryption")
    thermostat.transport.client = None
    thermostat.ready = False
    with (
        patch(
            "custom_components.panasonic_hc.transport.establish_connection",
            AsyncMock(return_value=connected),
        ),
        patch("custom_components.panasonic_hc.transport.AUTHENTICATION_TIMEOUT", 0.01),
    ):
        with pytest.raises(PanasonicAuthenticationError, match="Insufficient encryption"):
            await thermostat.async_connect()
    connected.pair.assert_not_awaited()
    connected.unpair.assert_not_called()
    connected.disconnect.assert_awaited_once()
    assert thermostat.transport.last_failure_stage == "authenticating"


async def test_security_wait_cancellation_closes_without_pairing(thermostat, connected):

    started = asyncio.Event()

    async def subscribe(*args):
        started.set()
        raise BleakError("Insufficient authentication")

    connected.start_notify.side_effect = subscribe
    thermostat.transport.client = None
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ):
        task = asyncio.create_task(thermostat.async_connect())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    connected.pair.assert_not_awaited()
    connected.disconnect.assert_awaited_once()
    assert not thermostat._lock.locked()


async def test_api_authentication_error_is_not_mistaken_for_att_security(thermostat, connected):

    connected.start_notify.side_effect = BleakError(
        "Authenticated connection not ready yet for proxy"
    )
    thermostat.transport.client = None
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ):
        with pytest.raises(PanasonicHCException, match="Authenticated connection not ready"):
            await thermostat.async_connect()
    connected.start_notify.assert_awaited_once()
    connected.pair.assert_not_awaited()


@pytest.mark.parametrize("code", [5, 15])
async def test_wrapped_att_security_errors_wait_for_existing_session(thermostat, connected, code):

    cause = RuntimeError("GATT request failed")
    cause.error = SimpleNamespace(error=code)
    wrapper = BleakError("wrapped backend error")
    wrapper.__cause__ = cause
    connected.start_notify.side_effect = [wrapper, None]
    thermostat.transport.client = None
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ):
        await thermostat.async_connect()
    assert thermostat.available
    assert connected.start_notify.await_count == 2
    connected.pair.assert_not_awaited()
    await thermostat.async_disconnect()


async def test_retry_finishes_old_teardown_before_new_client(thermostat, connected):
    old = Mock(is_connected=True)
    old.disconnect = AsyncMock(side_effect=[TimeoutError("still closing"), None])
    thermostat.transport.client = old
    assert await thermostat.async_disconnect() is False
    assert thermostat.transport.client is old
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ) as establish:
        await thermostat.async_connect()
    assert old.disconnect.await_count == 2
    establish.assert_awaited_once()
    assert thermostat.available
    await thermostat.async_disconnect()


async def test_disconnect_error_after_link_down_releases_owner(thermostat, connected):
    async def disconnect():
        connected.is_connected = False
        raise AssertionError("backend cache cleanup")

    connected.disconnect.side_effect = disconnect
    assert await thermostat.async_disconnect() is True
    assert thermostat.transport.client is None


async def test_cancelled_disconnect_retains_owner_until_cleanup(thermostat, connected):
    started = asyncio.Event()

    async def disconnect():
        started.set()
        await asyncio.Event().wait()

    connected.disconnect.side_effect = disconnect
    task = asyncio.create_task(thermostat.async_disconnect())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert thermostat.transport.client is connected
    connected.disconnect.side_effect = None
    assert await thermostat.async_disconnect() is True


async def test_concurrent_disconnect_and_connect_do_not_overlap(thermostat, connected):
    started, closed = asyncio.Event(), asyncio.Event()
    old = Mock(is_connected=True)

    async def disconnect():
        started.set()
        await closed.wait()
        old.is_connected = False

    old.disconnect = AsyncMock(side_effect=disconnect)
    thermostat.transport.client = old
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection",
        AsyncMock(return_value=connected),
    ) as establish:
        closing = asyncio.create_task(thermostat.async_disconnect())
        await started.wait()
        opening = asyncio.create_task(thermostat.transport.connect())
        await asyncio.sleep(0)
        establish.assert_not_awaited()
        assert thermostat.transport.client is old
        closed.set()
        await closing
        await opening
    old.disconnect.assert_awaited_once()
    assert thermostat.transport.client is connected
    await thermostat.async_disconnect()


async def test_setup_cannot_replace_runtime_with_live_failed_session(thermostat, connected):
    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.panasonic_hc import RuntimeData, async_setup_entry

    connected.disconnect.side_effect = TimeoutError("still closing")
    previous = RuntimeData(thermostat)
    entry = SimpleNamespace(unique_id=thermostat.mac_address, data={}, runtime_data=previous)
    with patch("custom_components.panasonic_hc.PanasonicHC") as constructor:
        with pytest.raises(ConfigEntryNotReady, match="previous BLE session"):
            await async_setup_entry(Mock(), entry)
    constructor.assert_not_called()
    assert entry.runtime_data is previous


async def test_failed_setup_keeps_runtime_for_next_cleanup_attempt(device):
    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.panasonic_hc import async_setup_entry

    controller = Mock()
    controller.async_connect = AsyncMock(side_effect=PanasonicHCException("setup failed"))
    entry = SimpleNamespace(unique_id=device.address, data={})
    with (
        patch(
            "custom_components.panasonic_hc.bluetooth.async_ble_device_from_address",
            return_value=device,
        ),
        patch("custom_components.panasonic_hc.PanasonicHC", return_value=controller),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(Mock(), entry)
    assert entry.runtime_data.thermostat is controller


async def test_unload_refuses_to_forget_live_failed_session(thermostat, connected):
    from custom_components.panasonic_hc import RuntimeData, async_unload_entry

    connected.disconnect.side_effect = TimeoutError("still closing")
    hass = Mock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry = SimpleNamespace(runtime_data=RuntimeData(thermostat))
    assert await async_unload_entry(hass, entry) is False
    assert thermostat.transport.client is connected


async def test_flow_retry_cannot_replace_live_validation_controller(device):
    from custom_components.panasonic_hc.config_flow import PanasonicHCConfigFlow

    previous = Mock()
    previous.async_disconnect = AsyncMock(return_value=False)
    flow = PanasonicHCConfigFlow()
    flow.hass = Mock()
    flow.mac_address = device.address
    flow._validation_controller = previous
    with patch("custom_components.panasonic_hc.config_flow.PanasonicHC") as constructor:
        assert await flow._validate_connection() == "cannot_connect"
    constructor.assert_not_called()
    assert flow._validation_controller is previous


@pytest.mark.parametrize("disconnect_during_retry", [False, True])
async def test_security_disconnect_preserves_cause_and_does_not_try_other_adapters(
    thermostat, connected, disconnect_during_retry
):
    from custom_components.panasonic_hc.errors import PanasonicAuthenticationError

    security_error = BleakError("Insufficient authentication")
    calls = 0

    async def subscribe(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            if not disconnect_during_retry:
                connected.is_connected = False
            raise security_error
        connected.is_connected = False
        raise BleakError("Not connected")

    async def establish(*args, route_policy, **kwargs):
        route_policy.selected = "BONDED_PROXY"
        route_policy.candidates = {"BONDED_PROXY", "OTHER_ADAPTER"}
        return connected

    connected.start_notify.side_effect = subscribe
    thermostat.transport.client = None
    thermostat.transport.routes.preferred = "BONDED_PROXY"
    thermostat.ready = False
    with patch(
        "custom_components.panasonic_hc.transport.establish_connection", side_effect=establish
    ) as create:
        with pytest.raises(
            PanasonicAuthenticationError, match="Insufficient authentication"
        ) as exc:
            await thermostat.async_connect()
    assert exc.value.__cause__ is security_error
    create.assert_awaited_once()
    assert thermostat.transport.last_failure_stage == "authenticating"
    connected.pair.assert_not_awaited()
    connected.unpair.assert_not_called()
