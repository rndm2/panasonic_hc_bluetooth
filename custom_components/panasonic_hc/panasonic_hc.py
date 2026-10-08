"""Serialized BLE operations and validated climate status."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

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
RESPONSE_TIMEOUT = 15
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
        if self._device_callback is not None:
            device = self._device_callback()
            if device is None:
                raise PanasonicHCException("No connectable Bluetooth route")
            self.device = device
        try:
            async with asyncio.timeout(45):
                self._conn = await establish_connection(
                    BleakClientWithServiceCache,
                    self.device,
                    self.device.name or self.device.address,
                    disconnected_callback=self._disconnected,
                    ble_device_callback=self._resolve_device,
                )
                await asyncio.sleep(NOTIFY_SETTLE_DELAY)
                await self._conn.start_notify(BLE_CHAR_NOTIFY, self.on_notification)
                await asyncio.sleep(NOTIFY_SETTLE_DELAY)
                async with self._lock:
                    await self._request_status()
        except (BleakError, TimeoutError, PanasonicHCException) as err:
            await self.async_disconnect()
            raise PanasonicHCException("Could not initialize controller") from err
        except asyncio.CancelledError:
            await self.async_disconnect()
            raise
        self.disconnected_event.clear()

    async def async_disconnect(self) -> None:
        """Idempotent cleanup, also safe after a failed initial connection."""
        conn, self._conn = self._conn, None
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
                current = packet.curtemp
                # The original protocol has ambiguous temperature variants. Publish
                # unknown rather than freezing a stale reading indefinitely.
                if current is not None and (
                    not -40 <= current <= 70
                    or (
                        previous is not None
                        and previous.curtemp is not None
                        and abs(current - previous.curtemp) > 20
                    )
                ):
                    current = None
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

    async def _set(
        self, commands: list[PanasonicBLEParcel], expected: Callable[[Status], bool]
    ) -> None:
        async with self._lock:
            if not self.available:
                raise PanasonicHCException("Controller is not ready")
            for command in commands:
                await self._write(command)
            await self._request_status()
            if self.status is None or not expected(self.status):
                raise PanasonicHCException("Controller did not confirm requested setting")

    async def async_set_power(self, state: bool) -> None:
        await self._set([PanasonicBLEPower(int(state))], lambda s: s.power == state)

    async def async_set_temperature(self, temp: float) -> None:
        await self._set([PanasonicBLETemp(temp)], lambda s: s.settemp == temp)

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
