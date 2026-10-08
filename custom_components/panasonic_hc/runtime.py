"""Supervise connection recovery and polling for one config entry."""

import asyncio
import logging
from contextlib import suppress

from .panasonic_hc import PanasonicHC, PanasonicHCException

_LOGGER = logging.getLogger(__name__)


async def _async_run_thermostat(thermostat: PanasonicHC) -> None:
    delay = 5
    unavailable_logged = False
    try:
        while True:
            try:
                if not thermostat.available:
                    await thermostat.async_disconnect()
                    await thermostat.async_connect()
                await thermostat.async_get_status()
            except Exception as err:
                # Supervise the long-lived worker: an unexpected backend exception
                # must not leave the entry loaded with a permanently dead poller.
                # Cancellation is a BaseException and still propagates normally.
                if not unavailable_logged:
                    _LOGGER.warning(
                        "Panasonic controller unavailable: %s",
                        err,
                        exc_info=not isinstance(err, PanasonicHCException),
                    )
                    unavailable_logged = True
                await thermostat.async_disconnect()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)
                continue
            if unavailable_logged:
                _LOGGER.info("Panasonic controller connection restored")
                unavailable_logged = False
            delay = 5
            status = thermostat.status
            with suppress(TimeoutError):
                async with asyncio.timeout(60 if status is not None and status.power else 300):
                    await thermostat.disconnected_event.wait()
    finally:
        await thermostat.async_disconnect()
