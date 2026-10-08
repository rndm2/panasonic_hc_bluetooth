"""Per-controller route policy while retaining HA's BLE resource management.

HA 2026.10 exposes no preferred-source constructor parameter. Keep the small
wrapper selection extension isolated here; do not patch global classes, scanner
scores or enable/disable adapters. HA still allocates/releases slots and tracks
connections, including proxy removal during connect.
"""

from dataclasses import dataclass, field
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from habluetooth import HaBleakClientWrapper


@dataclass
class RoutePolicy:
    preferred: str | None = None
    excluded: set[str] = field(default_factory=set)
    selected: str | None = None


class PanasonicBleakClient(HaBleakClientWrapper):
    """Extend only this client's route selection, not HA's shared manager."""

    def __init__(self, device: BLEDevice, *, route_policy: RoutePolicy, **kwargs: Any) -> None:
        if not hasattr(HaBleakClientWrapper, "_async_get_backend_for_ble_device"):
            raise BleakError("This HA Bluetooth version lacks the route-selection extension")
        self._route_policy = route_policy
        self._target_address = device.address
        super().__init__(device, **kwargs)

    def _async_get_backend_for_ble_device(self, manager, scanner, ble_device):
        if scanner.source in self._route_policy.excluded:
            return None
        backend = super()._async_get_backend_for_ble_device(manager, scanner, ble_device)
        if backend is not None:
            self._route_policy.selected = scanner.source
        return backend

    def _async_get_best_available_backend_and_device(self, manager):
        preferred = self._route_policy.preferred
        if preferred is not None and preferred not in self._route_policy.excluded:
            for path in manager.async_scanner_devices_by_address(self._target_address, True):
                if path.scanner.source == preferred:
                    backend = self._async_get_backend_for_ble_device(
                        manager, path.scanner, path.ble_device
                    )
                    if backend is not None:
                        return backend
        # Preserve HA's scoring and slot checks for all remaining candidates.
        return super()._async_get_best_available_backend_and_device(manager)
