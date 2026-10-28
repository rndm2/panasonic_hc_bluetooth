"""Own one BLE session until its teardown has actually completed."""

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from .connection import PanasonicBleakClient, RoutePolicy
from .errors import (
    PanasonicAuthenticationError,
    PanasonicHCException,
    describe_error,
    is_authentication_error,
)

BLE_CHAR_WRITE = "4d200002-eff3-4362-b090-a04cab3f1da0"
BLE_CHAR_NOTIFY = "4d200003-eff3-4362-b090-a04cab3f1da0"
CONNECT_TIMEOUT = 25
# ESPHome may spend 20 seconds awaiting disconnect and 5 settling the slot.
DISCONNECT_TIMEOUT = 30
AUTHENTICATION_TIMEOUT = 60
SECURITY_RETRY_INTERVAL = 0.5
NOTIFY_SETTLE_DELAY = 0.5
_LOGGER = logging.getLogger(__name__)


class BLETransport:
    def __init__(
        self,
        device: BLEDevice,
        resolve: Callable[[], BLEDevice],
        received: Callable[[bytes], None],
        lost: Callable[[], None],
    ) -> None:
        self.device = device
        self._resolve = resolve
        self._received = received
        self._lost = lost
        self.client: PanasonicBleakClient | None = None
        self.stage = "disconnected"
        self.connect_attempts = 0
        self.accept_notifications = False
        self.routes = RoutePolicy()
        self.authentication_attempts = 0
        self.last_failure_stage: str | None = None
        self.last_disconnect_error: str | None = None
        self._disconnect_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    def _disconnected(self, client: PanasonicBleakClient) -> None:
        if client is self.client:
            self.accept_notifications = False
            self.stage = "disconnected"
            self._lost()

    async def _subscribe(self, client: PanasonicBleakClient, received: Callable) -> None:
        security_error: BleakError | None = None
        try:
            async with asyncio.timeout(AUTHENTICATION_TIMEOUT):
                while True:
                    if not client.is_connected:
                        raise BleakError("Controller disconnected while subscribing")
                    try:
                        await client.start_notify(BLE_CHAR_NOTIFY, received)
                        return
                    except BleakError as err:
                        if not is_authentication_error(err):
                            raise
                        if security_error is None:
                            self.authentication_attempts += 1
                        security_error = err
                        self.stage = "authenticating"
                        # Panasonic starts security itself. Keep this link alive
                        # while that procedure finishes; do not start new pairing.
                        await asyncio.sleep(SECURITY_RETRY_INTERVAL)
        except TimeoutError as err:
            self.last_failure_stage = "authenticating" if security_error else "subscribing"
            if security_error is not None:
                raise PanasonicAuthenticationError(
                    "Timed out waiting for the existing Bluetooth session to authenticate: "
                    f"{describe_error(security_error)}. Verify the controller's bond with "
                    "this adapter or proxy; automatic pairing was not requested."
                ) from security_error
            raise BleakError("Timed out subscribing to controller notifications") from err
        except BaseException:
            self.last_failure_stage = "authenticating" if security_error else "subscribing"
            raise

    async def connect(self) -> None:
        if not await self.disconnect():
            raise PanasonicHCException(
                "Cannot open a new connection while the previous BLE session is still closing: "
                f"{self.last_disconnect_error}"
            )
        self.connect_attempts += 1
        self.stage = "connecting"
        self.routes.selected = None
        self.last_failure_stage = None
        try:
            self.device = self._resolve()
            async with asyncio.timeout(CONNECT_TIMEOUT):
                self.client = await establish_connection(
                    PanasonicBleakClient,
                    self.device,
                    self.device.name or self.device.address,
                    disconnected_callback=self._disconnected,
                    max_attempts=1,
                    route_policy=self.routes,
                )
            client = self.client

            def received(_handle, data: bytearray) -> None:
                if self.accept_notifications and self.client is client and client.is_connected:
                    self._received(bytes(data))

            self.accept_notifications = True
            self.stage = "subscribing"
            await asyncio.sleep(NOTIFY_SETTLE_DELAY)
            await self._subscribe(client, received)
            await asyncio.sleep(NOTIFY_SETTLE_DELAY)
            self.stage = "connected"
            self.last_failure_stage = None
        except BaseException:
            if self.last_failure_stage is None:
                self.last_failure_stage = self.stage
            await self.disconnect()
            raise

    async def write(self, data: bytes, deadline_seconds: float) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Controller disconnected")
        async with asyncio.timeout(deadline_seconds):
            await client.write_gatt_char(BLE_CHAR_WRITE, data)

    async def disconnect(self) -> bool:
        async with self._disconnect_lock:
            self.accept_notifications = False
            client = self.client
            if client is None:
                self.stage = "disconnected"
                return True
            self.stage = "disconnecting"
            try:
                async with asyncio.timeout(DISCONNECT_TIMEOUT):
                    await client.disconnect()
            except Exception as err:
                if client.is_connected:
                    # Retain ownership. A retry must finish closing this client
                    # before it can create another client or select another route.
                    self.last_disconnect_error = describe_error(err)
                    self.stage = "disconnect_failed"
                    self._lost()
                    _LOGGER.debug(
                        "BLE session still open after cleanup: %s", self.last_disconnect_error
                    )
                    return False
                _LOGGER.debug(
                    "BLE cleanup reported an error after link closed: %s", describe_error(err)
                )
            if self.client is client:
                self.client = None
            self.last_disconnect_error = None
            self.stage = "disconnected"
            return True
