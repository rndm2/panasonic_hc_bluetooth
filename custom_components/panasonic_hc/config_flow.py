"""Bluetooth discovery and manual configuration."""

import logging
import re
from typing import Any

import probatio
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_MAC
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, MODEL
from .panasonic_hc import PanasonicHC, PanasonicHCException

_LOGGER = logging.getLogger(__name__)

SCHEMA_MAC = probatio.Schema({probatio.Required(CONF_MAC): str})


def validate_mac(mac: str) -> bool:
    return re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac) is not None


class PanasonicHCConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    mac_address: str

    async def _validate_connection(self) -> str | None:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.mac_address.upper(), connectable=True
        )
        if device is None:
            return "cannot_connect"
        thermostat = PanasonicHC(device, self.mac_address)
        try:
            await thermostat.async_connect()
        except PanasonicHCException:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating controller")
            return "unknown"
        finally:
            await thermostat.async_disconnect()
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is None:
            # Explicit user choice also works when the owner renamed the device
            # and its advertisement no longer matches CZ-RTC6*.
            configured = {entry.unique_id for entry in self._async_current_entries()}
            devices = {
                format_mac(info.address): info.name
                for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
                if info.name
                and not validate_mac(info.name)
                and format_mac(info.address) not in configured
            }
            self._mac_schema = probatio.Schema(
                {
                    probatio.Required(CONF_MAC): selector.SelectSelector(
                        {
                            "options": [
                                selector.SelectOptionDict(value=mac, label=f"{name} ({mac})")
                                for mac, name in sorted(devices.items(), key=lambda item: item[1])
                            ],
                            "custom_value": True,
                            "mode": selector.SelectSelectorMode.DROPDOWN,
                        }
                    )
                }
            )
        if user_input is not None:
            raw = user_input[CONF_MAC].strip()
            # Validate before format_mac: formatting is not input validation.
            if not validate_mac(raw):
                errors[CONF_MAC] = "invalid_mac_address"
            else:
                self.mac_address = format_mac(raw)
                await self.async_set_unique_id(self.mac_address)
                self._abort_if_unique_id_configured()
                if error := await self._validate_connection():
                    errors["base"] = error
                else:
                    return self._create_entry()
        return self.async_show_form(
            step_id="user", data_schema=getattr(self, "_mac_schema", SCHEMA_MAC), errors=errors
        )

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        self.mac_address = format_mac(discovery_info.address)
        await self.async_set_unique_id(self.mac_address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {CONF_MAC: self.mac_address}
        return await self.async_step_init()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._validate_connection():
                errors["base"] = error
            else:
                return self._create_entry()
        return self.async_show_form(
            step_id="init", errors=errors, description_placeholders={CONF_MAC: self.mac_address}
        )

    def _create_entry(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=f"{MODEL}_{self.mac_address[-8:].replace(':', '')}", data={}
        )
