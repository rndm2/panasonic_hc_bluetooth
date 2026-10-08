"""Manual Bluetooth reconnect without changing the controller settings."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PanasonicHCConfigEntry
from .const import DOMAIN
from .entity import PanasonicEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PanasonicHCConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PanasonicReconnect(entry)])


class PanasonicReconnect(PanasonicEntity, ButtonEntity):
    _attr_translation_key = "reconnect"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, entry: PanasonicHCConfigEntry) -> None:
        super().__init__(entry.runtime_data.thermostat)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{self._attr_unique_id}_reconnect"

    @property
    def available(self) -> bool:
        # Recovery must remain actionable while climate is unavailable.
        return True

    async def async_press(self) -> None:
        await self.hass.services.async_call(
            DOMAIN, "reconnect", {"entry_id": self._entry_id}, blocking=True
        )
