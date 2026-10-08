"""Serialized BLE operations and validated climate status."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from time import monotonic

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .panasonic_hc_proto import (
    FANSPEED,
    MODE,
    PanasonicBLEEnergySaving,
    PanasonicBLEFanMode,
    PanasonicBLEMode,
    PanasonicBLEParcel,
    PanasonicBLEPower,
    PanasonicBLEStatusReq,
    PanasonicBLETemp,
    ProtocolError,
)

MIN_TEMP = 16
MAX_TEMP = 32
BLE_CHAR_WRITE = "4d200002-eff3-4362-b090-a04cab3f1da0"
BLE_CHAR_NOTIFY = "4d200003-eff3-4362-b090-a04cab3f1da0"
CURRENT_TEMPERATURE_MAX_AGE = 600
RESPONSE_TIMEOUT = 15
COMMAND_QUEUE_TIMEOUT = 5
COMMAND_CONFIRM_TIMEOUT = 15
COMMAND_CONFIRM_INTERVAL = 0.5
# Preserve the controller settling delays from the working upstream connection path.
NOTIFY_SETTLE_DELAY = 0.5
_LOGGER = logging.getLogger(__name__)


class PanasonicHCException(Exception):
    """Controller communication or confirmation failed."""


@dataclass(frozen=True)
class Status:
    """Last complete climate status; optional fields may be absent on the wire."""

    power: bool
    mode: str
    powersave: bool | None
    curtemp: float | None
    settemp: float
    fanspeed: str


class PanasonicHC:
    """Own the connection and serialize complete request/response operations."""

    def __init__(
        self,
        ble_device: BLEDevice,
        mac_address: str,
        device_callback: Callable[[], BLEDevice | None] | None = None,
    ) -> None:
        self.device = ble_device
        self.mac_address = mac_address
        self._device_callback = device_callback
        self._on_update_callbacks: list[Callable[[], None]] = []
        self._conn: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self.disconnected_event = asyncio.Event()
        self._status_event = asyncio.Event()
        self.status: Status | None = None
        self.ready = False
        self.parse_errors = 0
        self._last_temperature: float | None = None
        self._temperature_updated_at: float | None = None
        self._temperature_expiry: asyncio.TimerHandle | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def current_temperature(self) -> float | None:
        """Return the last valid measurement only while it is fresh."""
        if (
            self._temperature_updated_at is None
            or monotonic() - self._temperature_updated_at >= CURRENT_TEMPERATURE_MAX_AGE
        ):
            return None
        return self._last_temperature

    def _expire_temperature(self) -> None:
        self._temperature_expiry = None
        self._temperature_updated_at = None
        if self.status is not None:
            self.status = replace(self.status, curtemp=None)
            self._publish()

    def _merge_temperature(self, value: float | None) -> float | None:
        # A partial/ambiguous packet is not evidence that the measurement changed.
        # Keep a separate validation anchor: rejecting one packet must not let the
        # next identical bad value bypass the jump check.
        if (
            value is not None
            and -40 <= value <= 70
            and (self._last_temperature is None or abs(value - self._last_temperature) <= 20)
        ):
            self._last_temperature = value
            self._temperature_updated_at = monotonic()
            if self._temperature_expiry is not None:
                self._temperature_expiry.cancel()
            if self._loop is not None:
                self._temperature_expiry = self._loop.call_later(
                    CURRENT_TEMPERATURE_MAX_AGE, self._expire_temperature
                )
        return self.current_temperature

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and self._conn.is_connected

    @property
    def available(self) -> bool:
        return self.ready and self.is_connected

    def register_update_callback(self, on_update: Callable[[], None]) -> None:
        self._on_update_callbacks.append(on_update)

    def unregister_update_callback(self, on_update: Callable[[], None]) -> None:
        if on_update in self._on_update_callbacks:
            self._on_update_callbacks.remove(on_update)

    def _publish(self) -> None:
        for callback in tuple(self._on_update_callbacks):
            try:
                callback()
            except Exception:
                _LOGGER.exception("Controller update callback failed")

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        if client is not self._conn:
            return
        self.ready = False
        self.disconnected_event.set()
        self._status_event.set()
        self._publish()

    def _resolve_device(self) -> BLEDevice:
        """Let HA select a currently connectable adapter/proxy on every retry."""
        if self._device_callback is not None:
            device = self._device_callback()
            if device is None:
                raise BleakError("No connectable Bluetooth route")
            self.device = device
        return self.device

    async def async_connect(self) -> None:
        """Refresh the adapter reference, connect and require a valid status."""
        self._loop = asyncio.get_running_loop()
        try:
            self.device = self._resolve_device()
            async with asyncio.timeout(45):
                self._conn = await establish_connection(
                    BleakClientWithServiceCache,
                    self.device,
                    self.device.name or self.device.address,
                    disconnected_callback=self._disconnected,
                )
                await asyncio.sleep(NOTIFY_SETTLE_DELAY)
                connection = self._conn

                def notification(handle: BleakGATTCharacteristic, data: bytearray) -> None:
                    # A backend may deliver queued notifications after disconnect.
                    if self._conn is connection:
                        self.on_notification(handle, data)

                await connection.start_notify(BLE_CHAR_NOTIFY, notification)
                await asyncio.sleep(NOTIFY_SETTLE_DELAY)
                async with self._lock:
                    await self._request_status()
        except (BleakError, TimeoutError, PanasonicHCException) as err:
            await self.async_disconnect()
            raise PanasonicHCException(f"Could not initialize controller: {err}") from err
        except BaseException:
            await self.async_disconnect()
            raise
        self.disconnected_event.clear()

    async def async_disconnect(self) -> None:
        """Idempotent cleanup, also safe after a failed initial connection."""
        conn, self._conn = self._conn, None
        if self._temperature_expiry is not None:
            self._temperature_expiry.cancel()
            self._temperature_expiry = None
        self._last_temperature = None
        self._temperature_updated_at = None
        if self.status is not None:
            self.status = replace(self.status, curtemp=None)
        self.ready = False
        self.disconnected_event.set()
        self._status_event.set()
        self._publish()
        if conn is not None:
            try:
                async with asyncio.timeout(10):
                    await conn.disconnect()
            except Exception:
                # Backend cleanup can raise AssertionError after a dropped BlueZ
                # connection. Never replace the original setup error/cancellation.
                _LOGGER.debug("Disconnect cleanup failed", exc_info=True)

    async def _write(self, command: PanasonicBLEParcel) -> None:
        if self._conn is None or not self._conn.is_connected:
            raise PanasonicHCException("Controller disconnected")
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                await self._conn.write_gatt_char(BLE_CHAR_WRITE, command.encode())
        except (BleakError, TimeoutError) as err:
            self.ready = False
            self.disconnected_event.set()
            self._publish()
            raise PanasonicHCException("Bluetooth write failed") from err

    async def _request_status(self) -> None:
        self._status_event.clear()
        await self._write(PanasonicBLEStatusReq())
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                await self._status_event.wait()
        except TimeoutError as err:
            self.ready = False
            self.disconnected_event.set()
            self._publish()
            raise PanasonicHCException("Timed out waiting for controller status") from err
        if not self.available:
            raise PanasonicHCException("Controller disconnected before status arrived")

    async def async_get_status(self) -> None:
        async with self._lock:
            await self._request_status()

    def on_notification(self, handle: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            parcel = PanasonicBLEParcel.parse(bytes(data))
        except (ProtocolError, ValueError, IndexError) as err:
            self.parse_errors += 1
            _LOGGER.debug("Ignoring invalid controller packet: %s", err)
            return
        updated = False
        for packet in parcel:
            if isinstance(packet, PanasonicBLEParcel.PanasonicBLEPacketStatus):
                previous = self.status
                current = self._merge_temperature(packet.curtemp)
                self.status = Status(
                    bool(packet.power),
                    packet.mode.name,
                    bool(packet.powersave)
                    if packet.powersave is not None
                    else (previous.powersave if previous is not None else None),
                    current,
                    packet.temp,
                    packet.fanspeed.name,
                )
                self.ready = True
                self._status_event.set()
                updated = True
        if updated:
            self._publish()

    @asynccontextmanager
    async def _command_slot(self) -> AsyncIterator[None]:
        try:
            async with asyncio.timeout(COMMAND_QUEUE_TIMEOUT):
                await self._lock.acquire()
        except TimeoutError as err:
            raise PanasonicHCException("Another controller operation is still in progress") from err
        try:
            yield
        finally:
            self._lock.release()

    async def _set(
        self, commands: list[PanasonicBLEParcel], expected: Callable[[Status], bool]
    ) -> None:
        async with self._command_slot():
            if not self.available:
                raise PanasonicHCException("Controller is not ready")
            for command in commands:
                await self._write(command)
            # The first reply can still describe the state before the write.
            # Do not resend the command: only poll until the setting is confirmed.
            try:
                async with asyncio.timeout(COMMAND_CONFIRM_TIMEOUT):
                    while True:
                        await self._request_status()
                        if self.status is not None and expected(self.status):
                            return
                        await asyncio.sleep(COMMAND_CONFIRM_INTERVAL)
            except TimeoutError as err:
                if not self._status_event.is_set():
                    # The outer deadline can expire before _request_status's own
                    # timeout. A silent controller still needs recovery.
                    self.ready = False
                    self.disconnected_event.set()
                    self._publish()
                raise PanasonicHCException("Controller did not confirm requested setting") from err

    async def async_set_power(self, state: bool) -> None:
        await self._set([PanasonicBLEPower(int(state))], lambda s: s.power == state)

    async def async_set_temperature(self, temp: float, hvac_mode: str | None = None) -> None:
        # Validate the entire combined HA request before sending any command.
        temperature = PanasonicBLETemp(temp)
        if hvac_mode is None:
            await self._set([temperature], lambda s: s.settemp == temp)
        elif hvac_mode == "off":
            await self._set(
                [temperature, PanasonicBLEPower(0)], lambda s: s.settemp == temp and not s.power
            )
        else:
            try:
                mode = MODE[hvac_mode].value
            except KeyError as err:
                raise ValueError("Invalid HVAC mode") from err
            await self._set(
                [PanasonicBLEPower(1), PanasonicBLEMode(mode), temperature],
                lambda s: s.settemp == temp and s.power and s.mode == hvac_mode,
            )

    async def async_set_mode(self, mode: str) -> None:
        try:
            value = MODE[mode].value
        except KeyError as err:
            raise ValueError("Invalid HVAC mode") from err
        await self._set(
            [PanasonicBLEPower(1), PanasonicBLEMode(value)], lambda s: s.power and s.mode == mode
        )

    async def async_set_fanmode(self, mode: str) -> None:
        try:
            value = FANSPEED[mode].value
        except KeyError as err:
            raise ValueError("Invalid fan mode") from err
        await self._set([PanasonicBLEFanMode(value)], lambda s: s.fanspeed == mode)

    async def async_set_energysaving(self, state: bool) -> None:
        await self._set([PanasonicBLEEnergySaving(state)], lambda s: s.powersave == state)
