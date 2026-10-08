"""Panasonic H&C Bluetooth integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass

import probatio
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .panasonic_hc import PanasonicHC, PanasonicHCException
from .runtime import _async_run_thermostat

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.CLIMATE, Platform.BUTTON]


@dataclass
class RuntimeData:
    """Entry-owned connection and polling task."""

    thermostat: PanasonicHC
    task: asyncio.Task[None] | None = None


type PanasonicHCConfigEntry = ConfigEntry[RuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Expose recovery even while the entry is waiting for a Bluetooth route."""
    reconnecting: set[str] = set()

    async def reconnect(call: ServiceCall) -> None:
        entry_id = call.data["entry_id"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Select a Panasonic H&C Bluetooth config entry")
        if entry.disabled_by is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_disabled"
            )
        if entry_id in reconnecting:
            raise HomeAssistantError("A reconnect is already in progress")
        reconnecting.add(entry_id)
        try:
            if not await hass.config_entries.async_reload(entry_id):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="reconnect_failed"
                )
        finally:
            reconnecting.discard(entry_id)

    hass.services.async_register(
        DOMAIN,
        "reconnect",
        reconnect,
        schema=probatio.Schema({probatio.Required("entry_id"): str}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PanasonicHCConfigEntry) -> bool:
    address = entry.unique_id
    if address is None:
        raise ConfigEntryNotReady("Missing Bluetooth address")

    def get_device():
        return bluetooth.async_ble_device_from_address(hass, address.upper(), connectable=True)

    device = get_device()
    if device is None:
        raise ConfigEntryNotReady("Controller has no connectable Bluetooth route")
    thermostat = PanasonicHC(device, address, get_device)
    thermostat.transport.routes.preferred = entry.data.get("preferred_source")
    try:
        await thermostat.async_connect()
    except PanasonicHCException as err:
        raise ConfigEntryNotReady(str(err)) from err
    if (source := thermostat.transport.routes.preferred) and source != entry.data.get(
        "preferred_source"
    ):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "preferred_source": source}
        )
    entry.runtime_data = RuntimeData(thermostat)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await thermostat.async_disconnect()
        raise
    entry.runtime_data.task = entry.async_create_background_task(
        hass, _async_run_thermostat(thermostat), "panasonic_hc_poll"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PanasonicHCConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = entry.runtime_data
    if runtime.task is not None:
        runtime.task.cancel()
        with suppress(asyncio.CancelledError):
            await runtime.task
    await runtime.thermostat.async_disconnect()
    return True
