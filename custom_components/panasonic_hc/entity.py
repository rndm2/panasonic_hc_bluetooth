"""Shared entity identity and subscription lifecycle."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo, format_mac
from homeassistant.helpers.entity import Entity

from .const import MANUFACTURER, MODEL
from .panasonic_hc import PanasonicHC


class PanasonicEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, thermostat: PanasonicHC) -> None:
        self._thermostat = thermostat
        # Preserve the original per-platform IDs and device connection identity.
        self._attr_unique_id = format_mac(thermostat.mac_address)
        self._attr_device_info = DeviceInfo(
            name=f"{MODEL}_{thermostat.mac_address[-8:].replace(':', '')}",
            manufacturer=MANUFACTURER,
            model=MODEL,
            connections={(CONNECTION_BLUETOOTH, thermostat.mac_address)},
        )

    @property
    def available(self) -> bool:
        return self._thermostat.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._thermostat.register_update_callback(self._async_on_updated)
        self.async_on_remove(
            lambda: self._thermostat.unregister_update_callback(self._async_on_updated)
        )

    @callback
    def _async_on_updated(self) -> None:
        self.async_write_ha_state()
