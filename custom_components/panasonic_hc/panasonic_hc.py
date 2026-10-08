"""Controller transactions joining the pure protocol/state model to BLE I/O."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from time import monotonic

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from . import protocol
from .state import CURRENT_TEMPERATURE_MAX_AGE, ControllerState, Status
from .transport import BLETransport

MIN_TEMP = 16
MAX_TEMP = 32
RESPONSE_TIMEOUT = 15
COMMAND_QUEUE_TIMEOUT = 5
COMMAND_CONFIRM_TIMEOUT = 15
COMMAND_CONFIRM_INTERVAL = 0.5
CONNECTION_DEADLINE = 90
_LOGGER = logging.getLogger(__name__)


class PanasonicHCException(Exception):
    """Controller communication or confirmation failed."""


class PanasonicHC:
    """Single-owner command queue; only received status can confirm a write."""

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
        self._lock = asyncio.Lock()
        self.disconnected_event = asyncio.Event()
        self._status_event = asyncio.Event()
        self.state = ControllerState()
        self.transport = BLETransport(
            ble_device, self._resolve_device, self.on_notification, self._lost
        )
        self.ready = False
        self.parse_errors = 0
        self.command_failures = 0
        self._temperature_expiry: asyncio.TimerHandle | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def status(self) -> Status | None:
        return self.state.status

    @property
    def current_temperature(self) -> float | None:
        return self.state.current_temperature(monotonic())

    @property
    def is_connected(self) -> bool:
        return self.transport.connected

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

    def _cancel_temperature_timer(self) -> None:
        if self._temperature_expiry is not None:
            self._temperature_expiry.cancel()
            self._temperature_expiry = None

    def _expire_temperature(self) -> None:
        self._temperature_expiry = None
        self.state.expire_temperature()
        self._publish()

    def _lost(self) -> None:
        self.transport.accept_notifications = False
        self.ready = False
        self._cancel_temperature_timer()
        self.state.disconnected()
        self.disconnected_event.set()
        self._status_event.set()
        self._publish()

    def _resolve_device(self) -> BLEDevice:
        if self._device_callback is not None:
            device = self._device_callback()
            if device is None:
                raise BleakError("No connectable Bluetooth route")
            self.device = device
        return self.device

    async def async_connect(self) -> None:
        async with self._lock:
            if self.available:
                return
            self._loop = asyncio.get_running_loop()
            routes = self.transport.routes
            routes.excluded.clear()
            try:
                async with asyncio.timeout(CONNECTION_DEADLINE):
                    while True:
                        self._lost()
                        try:
                            await self.transport.connect()
                            await self._request_status()
                            if not self.available:
                                raise PanasonicHCException(
                                    "Controller disconnected during initialization"
                                )
                        except (BleakError, OSError, TimeoutError, PanasonicHCException) as err:
                            failed_source = routes.selected
                            await self.async_disconnect()
                            if failed_source is None or failed_source in routes.excluded:
                                raise
                            routes.excluded.add(failed_source)
                            _LOGGER.debug(
                                "Controller route %s failed readiness: %s; trying another route",
                                failed_source,
                                err,
                            )
                            continue
                        # Only a complete status handshake makes a route preferred.
                        routes.preferred = routes.selected
                        self.disconnected_event.clear()
                        return
            except (BleakError, OSError, TimeoutError, PanasonicHCException) as err:
                await self.async_disconnect()
                raise PanasonicHCException(f"Could not initialize controller: {err}") from err
            except BaseException:
                await self.async_disconnect()
                raise

    async def async_disconnect(self) -> None:
        self._lost()
        await self.transport.disconnect()

    async def _write(self, command: protocol.Parcel) -> None:
        try:
            await self.transport.write(command.encode(), RESPONSE_TIMEOUT)
        except Exception as err:
            self._lost()
            raise PanasonicHCException("Bluetooth write failed") from err

    async def _request_status(self) -> None:
        generation = self.state.generation
        self._status_event.clear()
        await self._write(protocol.status_request())
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                await self._status_event.wait()
        except TimeoutError as err:
            self._lost()
            raise PanasonicHCException("Timed out waiting for controller status") from err
        if not self.available or self.state.generation == generation:
            raise PanasonicHCException("Controller disconnected before status arrived")

    async def async_get_status(self) -> None:
        async with self._lock:
            await self._request_status()

    def on_notification(self, data: bytes) -> None:
        try:
            reports = protocol.Parcel.parse(data).status_reports()
        except protocol.ProtocolError as err:
            self.parse_errors += 1
            _LOGGER.debug("Ignoring invalid controller packet: %s", err)
            return
        for report in reports:
            if self.state.apply(report, monotonic()) and self._loop is not None:
                self._cancel_temperature_timer()
                self._temperature_expiry = self._loop.call_later(
                    CURRENT_TEMPERATURE_MAX_AGE, self._expire_temperature
                )
        if reports:
            self.ready = True
            self._status_event.set()
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
        self, commands: list[protocol.Parcel], expected: Callable[[Status], bool]
    ) -> None:
        try:
            async with self._command_slot():
                if not self.available:
                    raise PanasonicHCException("Controller is not ready")
                # Bound the whole transaction, including all writes, not just its
                # confirmation phase. Never resend writes after an uncertain result.
                writes_complete = False
                self._status_event.clear()
                try:
                    async with asyncio.timeout(COMMAND_CONFIRM_TIMEOUT):
                        for command in commands:
                            await self._write(command)
                        writes_complete = True
                        while True:
                            await self._request_status()
                            if self.status is not None and expected(self.status):
                                return
                            await asyncio.sleep(COMMAND_CONFIRM_INTERVAL)
                except TimeoutError as err:
                    if not writes_complete or not self._status_event.is_set():
                        self._lost()
                    raise PanasonicHCException(
                        "Controller did not confirm requested setting"
                    ) from err
                except asyncio.CancelledError:
                    # A write may have reached the device. Force recovery/status
                    # read before another command can trust the old session.
                    self._lost()
                    raise
        except PanasonicHCException:
            self.command_failures += 1
            raise

    async def async_set_power(self, state: bool) -> None:
        await self._set([protocol.power(state)], lambda s: s.power == state)

    async def async_set_temperature(self, temp: float, hvac_mode: str | None = None) -> None:
        temperature = protocol.temperature(temp)
        if hvac_mode is None:
            await self._set([temperature], lambda s: s.settemp == temp)
        elif hvac_mode == "off":
            await self._set(
                [temperature, protocol.power(False)], lambda s: s.settemp == temp and not s.power
            )
        else:
            mode = protocol.mode(hvac_mode)
            await self._set(
                [protocol.power(True), mode, temperature],
                lambda s: s.settemp == temp and s.power and s.mode == hvac_mode,
            )

    async def async_set_mode(self, mode: str) -> None:
        command = protocol.mode(mode)
        await self._set([protocol.power(True), command], lambda s: s.power and s.mode == mode)

    async def async_set_fanmode(self, mode: str) -> None:
        await self._set([protocol.fan(mode)], lambda s: s.fanspeed == mode)

    async def async_set_energysaving(self, state: bool) -> None:
        await self._set([protocol.eco(state)], lambda s: s.powersave == state)
