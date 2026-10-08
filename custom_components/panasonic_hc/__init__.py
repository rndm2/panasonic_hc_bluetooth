"""Panasonic H&C Bluetooth integration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

import probatio
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .panasonic_hc import PanasonicHC, PanasonicHCException

PLATFORMS = [Platform.CLIMATE, Platform.BUTTON]
_LOGGER = logging.getLogger(__name__)


@dataclass
class RuntimeData:
    """Entry-owned connection and polling task."""

    thermostat: PanasonicHC
    task: asyncio.Task[None] | None = None


type PanasonicHCConfigEntry = ConfigEntry[RuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Expose recovery even while the entry is waiting for a Bluetooth route."""
    locks: dict[str, asyncio.Lock] = {}

    async def reconnect(call: ServiceCall) -> None:
        entry_id = call.data["entry_id"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Select a Panasonic H&C Bluetooth config entry")
        lock = locks.setdefault(entry_id, asyncio.Lock())
        if lock.locked():
            raise HomeAssistantError("A reconnect is already in progress")
        async with lock:
            if not await hass.config_entries.async_reload(entry_id):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="reconnect_failed"
                )

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
    try:
        await thermostat.async_connect()
    except PanasonicHCException as err:
        raise ConfigEntryNotReady(str(err)) from err
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


async def _async_run_thermostat(thermostat: PanasonicHC) -> None:
    delay = 5
    unavailable_logged = False
    try:
        while True:
            try:
                if not thermostat.available:
                    await thermostat.async_disconnect()
                    await thermostat.async_connect()
                await thermostat.async_get_status()
            except PanasonicHCException as err:
                if not unavailable_logged:
                    _LOGGER.warning("Panasonic controller unavailable: %s", err)
                    unavailable_logged = True
                await thermostat.async_disconnect()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)
                continue
            if unavailable_logged:
                _LOGGER.info("Panasonic controller connection restored")
                unavailable_logged = False
            delay = 5
            status = thermostat.status
            with suppress(TimeoutError):
                async with asyncio.timeout(60 if status is not None and status.power else 300):
                    await thermostat.disconnected_event.wait()
    finally:
        await thermostat.async_disconnect()
