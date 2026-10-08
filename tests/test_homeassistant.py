"""Exercise HA entities and lifecycle against real Home Assistant classes."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError

from custom_components.panasonic_hc import RuntimeData, async_setup_entry, async_unload_entry
from custom_components.panasonic_hc.climate import PanasonicHCClimate
from custom_components.panasonic_hc.config_flow import PanasonicHCConfigFlow
from custom_components.panasonic_hc.panasonic_hc import PanasonicHCException


def test_stable_identity(thermostat):
    climate = PanasonicHCClimate(thermostat)
    assert climate.unique_id == "aa:bb:cc:dd:ee:ff"


async def test_service_error_propagates(thermostat):
    climate = PanasonicHCClimate(thermostat)
    with pytest.raises(HomeAssistantError):
        await climate.async_turn_on()
    with pytest.raises(ServiceValidationError):
        await climate.async_set_temperature(temperature=14)
    with pytest.raises(ServiceValidationError):
        await climate.async_set_preset_mode("invalid")


async def test_temperature_uses_confirmed_state(thermostat, connected):
    climate = PanasonicHCClimate(thermostat)
    with pytest.raises(HomeAssistantError):
        await climate.async_set_temperature(temperature=23)
    assert climate.target_temperature == 22
    assert climate.current_temperature == 23


async def test_setup_unavailable_route():
    entry = SimpleNamespace(unique_id="aa:bb:cc:dd:ee:ff")
    with patch(
        "custom_components.panasonic_hc.bluetooth.async_ble_device_from_address", return_value=None
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(Mock(), entry)


async def test_setup_failed_status_retries(device):
    entry = SimpleNamespace(unique_id=device.address)
    with (
        patch(
            "custom_components.panasonic_hc.bluetooth.async_ble_device_from_address",
            return_value=device,
        ),
        patch(
            "custom_components.panasonic_hc.PanasonicHC.async_connect",
            AsyncMock(side_effect=PanasonicHCException("no status")),
        ),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(Mock(), entry)


async def test_unload_cancels_poll_before_disconnect(thermostat):
    task = asyncio.create_task(asyncio.Event().wait())
    entry = SimpleNamespace(runtime_data=RuntimeData(thermostat, task))
    hass = Mock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await async_unload_entry(hass, entry)
    assert task.cancelled()
    assert not thermostat.available


async def test_failed_unload_keeps_connection(thermostat, connected):
    entry = SimpleNamespace(runtime_data=RuntimeData(thermostat))
    hass = Mock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    assert not await async_unload_entry(hass, entry)
    connected.disconnect.assert_not_awaited()


async def test_flow_invalid_mac_has_friendly_error():
    flow = PanasonicHCConfigFlow()
    result = await flow.async_step_user({"mac": "GG:11:22:33:44:55"})
    assert result["errors"] == {"mac": "invalid_mac_address"}


async def test_flow_connection_cleanup(device):
    flow = PanasonicHCConfigFlow()
    flow.hass = Mock()
    flow.mac_address = device.address
    with (
        patch(
            "custom_components.panasonic_hc.config_flow.bluetooth.async_ble_device_from_address",
            return_value=device,
        ),
        patch(
            "custom_components.panasonic_hc.config_flow.PanasonicHC.async_connect",
            AsyncMock(side_effect=PanasonicHCException()),
        ),
        patch(
            "custom_components.panasonic_hc.config_flow.PanasonicHC.async_disconnect", AsyncMock()
        ) as disconnect,
    ):
        assert await flow._validate_connection() == "cannot_connect"
        disconnect.assert_awaited_once()


async def test_entry_setup_starts_one_task_and_unloads(hass, device, thermostat, connected):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="panasonic_hc", unique_id=device.address, data={})
    entry.add_to_hass(hass)
    thermostat.async_connect = AsyncMock()
    thermostat.async_get_status = AsyncMock()
    with (
        patch(
            "custom_components.panasonic_hc.bluetooth.async_ble_device_from_address",
            return_value=device,
        ),
        patch("custom_components.panasonic_hc.PanasonicHC", return_value=thermostat),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)),
    ):
        assert await async_setup_entry(hass, entry)
        await asyncio.sleep(0)
        assert entry.runtime_data.thermostat is thermostat
        assert entry.runtime_data.task is not None
        assert await async_unload_entry(hass, entry)
        assert entry.runtime_data.task.done()


async def test_flow_duplicate_and_success(hass, device):
    from homeassistant.data_entry_flow import AbortFlow
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="panasonic_hc", unique_id=device.address.lower(), data={})
    entry.add_to_hass(hass)
    flow = PanasonicHCConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.handler = "panasonic_hc"
    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user({"mac": device.address})
    flow2 = PanasonicHCConfigFlow()
    flow2.hass = hass
    flow2.context = {"source": "user"}
    flow2.handler = "panasonic_hc"
    with patch.object(flow2, "_validate_connection", AsyncMock(return_value=None)):
        result = await flow2.async_step_user({"mac": "00:11:22:33:44:55"})
    assert result["type"] == "create_entry"
    assert result["data"] == {}
    assert flow2.unique_id == "00:11:22:33:44:55"


async def test_diagnostics_do_not_expose_address(thermostat, connected):
    from custom_components.panasonic_hc.diagnostics import async_get_config_entry_diagnostics

    entry = SimpleNamespace(runtime_data=RuntimeData(thermostat))
    result = await async_get_config_entry_diagnostics(Mock(), entry)
    assert result["available"] is True
    assert thermostat.mac_address not in str(result)


async def test_entity_subscription_removed(hass, thermostat, connected):
    climate = PanasonicHCClimate(thermostat)
    climate.hass = hass
    climate.entity_id = "climate.test"
    await climate.async_added_to_hass()
    assert len(thermostat._on_update_callbacks) == 1
    await climate.async_remove(force_remove=True)
    assert not thermostat._on_update_callbacks


async def test_manual_reconnect_service_works_without_loaded_runtime(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.panasonic_hc import async_setup

    entry = MockConfigEntry(domain="panasonic_hc", unique_id="aa:bb:cc:dd:ee:ff", data={})
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as reload:
        await hass.services.async_call(
            "panasonic_hc", "reconnect", {"entry_id": entry.entry_id}, blocking=True
        )
    reload.assert_awaited_once_with(entry.entry_id)


async def test_reconnect_rejects_other_integrations(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.panasonic_hc import async_setup

    entry = MockConfigEntry(domain="other", data={})
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "panasonic_hc", "reconnect", {"entry_id": entry.entry_id}, blocking=True
        )


async def test_reconnect_failure_surfaces(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.panasonic_hc import async_setup

    entry = MockConfigEntry(domain="panasonic_hc", data={})
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    with (
        patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=False)),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            "panasonic_hc", "reconnect", {"entry_id": entry.entry_id}, blocking=True
        )


async def test_reconnect_button_available_offline(hass, thermostat):
    from custom_components.panasonic_hc.button import PanasonicReconnect

    entry = SimpleNamespace(entry_id="test", runtime_data=RuntimeData(thermostat))
    button = PanasonicReconnect(entry)
    button.hass = hass
    assert button.available
    assert button.unique_id == "aa:bb:cc:dd:ee:ff_reconnect"
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        await button.async_press()
    call.assert_awaited_once_with("panasonic_hc", "reconnect", {"entry_id": "test"}, blocking=True)


async def test_reconnect_rejects_overlapping_requests(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.panasonic_hc import async_setup

    entry = MockConfigEntry(domain="panasonic_hc", data={})
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    started = asyncio.Event()
    finish = asyncio.Event()

    async def reload(entry_id):
        started.set()
        await finish.wait()
        return True

    with patch.object(hass.config_entries, "async_reload", side_effect=reload):
        first = asyncio.create_task(
            hass.services.async_call(
                "panasonic_hc", "reconnect", {"entry_id": entry.entry_id}, blocking=True
            )
        )
        await started.wait()
        try:
            with pytest.raises(HomeAssistantError, match="already in progress"):
                await hass.services.async_call(
                    "panasonic_hc", "reconnect", {"entry_id": entry.entry_id}, blocking=True
                )
        finally:
            finish.set()
            await first


async def test_diagnostics_before_successful_setup():
    from custom_components.panasonic_hc.diagnostics import async_get_config_entry_diagnostics

    result = await async_get_config_entry_diagnostics(Mock(), SimpleNamespace())
    assert result == {
        "connected": False,
        "available": False,
        "has_status": False,
        "invalid_packets": 0,
    }


async def test_set_temperature_forwards_optional_hvac_mode(thermostat):
    thermostat.async_set_temperature = AsyncMock()
    climate = PanasonicHCClimate(thermostat)
    await climate.async_set_temperature(temperature=25, hvac_mode="heat")
    thermostat.async_set_temperature.assert_awaited_once_with(25, "heat")


async def test_reconnect_rejects_disabled_entry(hass):
    from homeassistant.config_entries import ConfigEntryDisabler
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.panasonic_hc import async_setup

    entry = MockConfigEntry(domain="panasonic_hc", data={}, disabled_by=ConfigEntryDisabler.USER)
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "panasonic_hc", "reconnect", {"entry_id": entry.entry_id}, blocking=True
            )
        reload.assert_not_awaited()


async def test_poll_worker_recovers_after_unexpected_backend_error():
    from custom_components.panasonic_hc import _async_run_thermostat

    thermostat = Mock()
    thermostat.available = True
    thermostat.async_get_status = AsyncMock(
        side_effect=[RuntimeError("backend error"), asyncio.CancelledError()]
    )
    thermostat.async_disconnect = AsyncMock()
    with patch("custom_components.panasonic_hc.asyncio.sleep", AsyncMock()) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await _async_run_thermostat(thermostat)
    assert thermostat.async_get_status.await_count == 2
    sleep.assert_awaited_once_with(5)
    assert thermostat.async_disconnect.await_count == 2
