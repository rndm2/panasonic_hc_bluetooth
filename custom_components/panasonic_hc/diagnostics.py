"""Diagnostics without Bluetooth addresses or raw payloads."""

from homeassistant.core import HomeAssistant

from . import PanasonicHCConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PanasonicHCConfigEntry
) -> dict:
    device = entry.runtime_data.thermostat
    return {
        "connected": device.is_connected,
        "available": device.available,
        "has_status": device.status is not None,
        "invalid_packets": device.parse_errors,
    }
