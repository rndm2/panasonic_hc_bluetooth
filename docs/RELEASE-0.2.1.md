# Panasonic H&C Bluetooth 0.2.1

Fixes adding a controller after deleting its integration when HA selects a Bluetooth adapter that connects but cannot complete the Panasonic handshake. The component now tries other available routes and remembers the route that returned a valid status. Setup and reconnect prefer that route, with fallback when unavailable.

No adapters or proxies are disabled or restarted by this mechanism. Existing domain, device and entity identity remain unchanged. Pairing bonds remain managed by the Bluetooth backend.

Validation: 117 tests, 92% coverage, Ruff and mypy. The owner successfully added the real controller through HA after deletion; the integration loaded through the bonded proxy with all three adapters enabled. Manual reconnect also succeeded through that proxy. See the [validation record](https://github.com/rndm2/panasonic_hc_bluetooth/blob/main/docs/VALIDATION.md).

The isolated route selector extends protected HA Bluetooth client hooks, tested on HA 2026.10.0. Review compatibility on HA upgrades. Install via HACS and restart Home Assistant; keep the existing entry.
