# Changelog

All notable changes are documented here. Versions follow Semantic Versioning.

## [Unreleased]

## [0.1.2] - 2026-10-09

### Fixed

- Preserve current temperature across partial/ambiguous status packets instead of flashing unknown.
- Keep the validation anchor separate from displayed state so repeated invalid readings cannot bypass it.
- Expire measurements after ten minutes without a valid update, even without new notifications;
  cancel expiry on disconnect and discard old measurements when the connection is closed.
- Honor optional HVAC mode in combined temperature actions and validate all arguments before writes.
- Bound command queue waiting to five seconds; expose the actual failure reason in HA action errors.
- Reject reconnect for disabled entries instead of reporting success without a connection.
- Recover the background polling worker after unexpected backend exceptions, with traceback logging.


## [0.1.1] - 2026-10-08

### Fixed

- Wait up to 15 seconds for command confirmation when the first status reply still contains
  the previous setting. Only status requests are repeated, never the HVAC command.
- A BlueZ backend assertion during disconnect cleanup could mask the original dropped
  connection and prevent Home Assistant from retrying setup. Cleanup is now best-effort
  for backend exceptions while cancellation continues to propagate.
- Ignore queued notifications from a previous connection after disconnect.
- Clean up connections on unexpected setup exceptions without masking the exception.
- Allow diagnostics before successful entry setup and include the cause of connection errors.
- Remove the unused retry-connector callback argument and clarify that HA chooses the route;
  refreshing a device lookup does not force a different proxy.
- Add regression tests for cleanup, stale notifications and unavailable diagnostics.

## [0.1.0] - 2026-10-08

### Added

- Manual **Reconnect Bluetooth** device button and `panasonic_hc.reconnect` action, usable
  from Developer Tools even when the config entry is retrying initial setup.
- Packet, MAC validation, BLE lifecycle, service-error, identity and reconnect regression tests.
- Ruff, formatting, mypy, pytest, HACS validation and hassfest CI checks.
- Redacted integration diagnostics and installation, migration and recovery documentation.

### Changed

- Independent repository `rndm2/panasonic_hc_bluetooth`, maintained by @rndm2 with original
  David Collett attribution and Git history retained.
- Display name **Panasonic H&C Bluetooth**, version **0.1.0**; minimum tested HA **2026.10.0**.
- Use typed `ConfigEntry.runtime_data` and shared entity lifecycle/availability.
- Refresh connectable Bluetooth route on connection attempts, including proxy retries.
- Serialize commands and require matching returned state; surface errors to HA actions.
- Retry failed connections with bounded backoff; wake polling immediately on disconnect.

### Fixed

- Invalid MAC strings crashing configuration or passing validation incorrectly.
- Packet length/checksum/header handling and the outdoor-temperature packet constructor.
- Missing initial status, missing connection and cancelled/failed connection cleanup.
- Deterministic unload, notification unsubscription and concurrent reconnect handling.
- Target-temperature display using a different attribute from the command path.
- Preserve the maintainer's earlier short-status, optional powersave, auto-mode alias,
  UART keepalive and all-mode fan-control fixes, with regression tests.

### Removed

- **All energy tracking**: Daily Energy sensor, consumption requests/parser and snapshots.
  Existing stored history/statistics are not deleted.

### Compatibility

The internal domain `panasonic_hc`, climate unique ID and Bluetooth device identity remain
unchanged. Keep the existing config entry during migration. The old energy entity may remain
unavailable in the registry. No new license is applied to inherited, unlicensed upstream code.

[Unreleased]: https://github.com/rndm2/panasonic_hc_bluetooth/compare/v0.1.2...HEAD
[0.1.0]: https://github.com/rndm2/panasonic_hc_bluetooth/releases/tag/v0.1.0
[0.1.1]: https://github.com/rndm2/panasonic_hc_bluetooth/releases/tag/v0.1.1

[0.1.2]: https://github.com/rndm2/panasonic_hc_bluetooth/releases/tag/v0.1.2
