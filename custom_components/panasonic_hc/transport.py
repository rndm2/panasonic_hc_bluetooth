"""One BLE session, with bounded I/O and stale-callback isolation."""

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .connection import PanasonicBleakClient, RoutePolicy

BLE_CHAR_WRITE = "4d200002-eff3-4362-b090-a04cab3f1da0"
BLE_CHAR_NOTIFY = "4d200003-eff3-4362-b090-a04cab3f1da0"
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

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    def _disconnected(self, client: PanasonicBleakClient) -> None:
        if client is self.client:
            self.accept_notifications = False
            self.stage = "disconnected"
            self._lost()

    async def connect(self) -> None:
        await self.disconnect()
        self.connect_attempts += 1
        self.stage = "connecting"
        self.routes.selected = None
        self.device = self._resolve()
        try:
            async with asyncio.timeout(25):
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
                await client.start_notify(BLE_CHAR_NOTIFY, received)
                await asyncio.sleep(NOTIFY_SETTLE_DELAY)
                self.stage = "connected"
        except BaseException:
            await self.disconnect()
            raise

    async def write(self, data: bytes, deadline_seconds: float) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Controller disconnected")
        async with asyncio.timeout(deadline_seconds):
            await client.write_gatt_char(BLE_CHAR_WRITE, data)

    async def disconnect(self) -> None:
        self.accept_notifications = False
        client, self.client = self.client, None
        self.stage = "disconnected"
        if client is not None:
            try:
                async with asyncio.timeout(10):
                    await client.disconnect()
            except Exception:
                _LOGGER.debug("BLE cleanup failed", exc_info=True)
