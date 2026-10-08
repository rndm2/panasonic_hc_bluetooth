"""Connection health and route candidates, without addresses or raw frames."""

from time import monotonic

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from . import PanasonicHCConfigEntry


def _routes(hass: HomeAssistant, address: str) -> list[dict]:
    paths = bluetooth.async_scanner_devices_by_address(hass, address.upper(), connectable=True)
    result = []
    for path in paths:
        scanner = path.scanner
        allocations = scanner.get_allocations()
        result.append(
            {
                "remote": scanner.connector is not None,
                "rssi": path.advertisement.rssi,
                "connect_failures": scanner.connection_failures(address.upper()),
                "free_slots": allocations.free if allocations else None,
                "total_slots": allocations.slots if allocations else None,
            }
        )
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PanasonicHCConfigEntry
) -> dict:
    runtime = getattr(entry, "runtime_data", None)
    result: dict = {
        "connected": False,
        "available": False,
        "has_status": False,
        "invalid_packets": 0,
    }
    if runtime is not None:
        controller = runtime.thermostat
        now = monotonic()
        result.update(
            {
                "connected": controller.is_connected,
                "available": controller.available,
                "has_status": controller.status is not None,
                "invalid_packets": controller.parse_errors,
                "rejected_temperature_samples": controller.state.rejected_temperatures,
                "connection_stage": controller.transport.stage,
                "connection_attempts": controller.transport.connect_attempts,
                "command_failures": controller.command_failures,
                "status_age_seconds": (
                    round(now - controller.state.status_at, 1)
                    if controller.state.status_at is not None
                    else None
                ),
                "temperature_age_seconds": (
                    round(now - controller.state.temperature_at, 1)
                    if controller.state.temperature_at is not None
                    else None
                ),
            }
        )
    if address := getattr(entry, "unique_id", None):
        # HA scanner interfaces can change; optional diagnostics must still be
        # downloadable if a future backend cannot provide route details.
        try:
            result["route_candidates"] = _routes(hass, address)
        except AttributeError, KeyError, RuntimeError:
            result["route_candidates"] = "unavailable"
    return result
