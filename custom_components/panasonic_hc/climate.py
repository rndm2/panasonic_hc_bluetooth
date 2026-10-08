"""Climate control with confirmed state and actionable service errors."""

from collections.abc import Awaitable
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_HALVES, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PanasonicHCConfigEntry
from .const import DOMAIN
from .entity import PanasonicEntity
from .panasonic_hc import MAX_TEMP, MIN_TEMP, PanasonicHCException


async def async_setup_entry(
    hass: HomeAssistant, entry: PanasonicHCConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PanasonicHCClimate(entry.runtime_data.thermostat)])


class PanasonicHCClimate(PanasonicEntity, ClimateEntity):
    _attr_name = "Thermostat"
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.FAN_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_precision = PRECISION_HALVES
    _attr_target_temperature_step = PRECISION_HALVES
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.AUTO,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_preset_modes = [PRESET_ECO, PRESET_NONE]

    @property
    def hvac_mode(self) -> HVACMode | None:
        status = self._thermostat.status
        return (HVACMode(status.mode) if status.power else HVACMode.OFF) if status else None

    @property
    def current_temperature(self) -> float | None:
        return self._thermostat.current_temperature

    @property
    def target_temperature(self) -> float | None:
        return self._thermostat.status.settemp if self._thermostat.status else None

    @property
    def fan_mode(self) -> str | None:
        return self._thermostat.status.fanspeed if self._thermostat.status else None

    @property
    def preset_mode(self) -> str | None:
        status = self._thermostat.status
        if status is None or status.powersave is None:
            return None
        return PRESET_ECO if status.powersave else PRESET_NONE

    async def _command(self, operation: Awaitable[None]) -> None:
        try:
            await operation
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            ) from err
        except PanasonicHCException as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"reason": str(err)},
            ) from err

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._command(
                self._thermostat.async_set_temperature(temperature, kwargs.get(ATTR_HVAC_MODE))
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._command(self._thermostat.async_set_power(False))
        else:
            await self._command(self._thermostat.async_set_mode(hvac_mode))

    async def async_turn_on(self) -> None:
        await self._command(self._thermostat.async_set_power(True))

    async def async_turn_off(self) -> None:
        await self._command(self._thermostat.async_set_power(False))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._command(self._thermostat.async_set_fanmode(fan_mode))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in self._attr_preset_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        await self._command(self._thermostat.async_set_energysaving(preset_mode == PRESET_ECO))
