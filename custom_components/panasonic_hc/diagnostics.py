"""Diagnostics without Bluetooth addresses or raw payloads."""

from homeassistant.core import HomeAssistant

from . import PanasonicHCConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PanasonicHCConfigEntry
) -> dict:
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return {"connected": False, "available": False, "has_status": False, "invalid_packets": 0}
    device = runtime.thermostat
    return {
        "connected": device.is_connected,
        "available": device.available,
        "has_status": device.status is not None,
        "invalid_packets": device.parse_errors,
    }
