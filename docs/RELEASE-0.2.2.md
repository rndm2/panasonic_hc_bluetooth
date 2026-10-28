# Panasonic H&C Bluetooth 0.2.2

Fixes BLE session ownership during reconnect: failed cleanup keeps the old client, and new setup/reconnect attempts wait for teardown instead of creating overlapping sessions. The disconnect deadline now covers ESPHome's response and slot-settlement budgets.

Protected notification errors wait for authentication on the existing connection. The integration does not initiate pair()/unpair(), accept a comparison code or restart proxies. A bond must already exist on the selected adapter or proxy.

Route errors retain their original causes, known exhaustion returns promptly, and diagnostics report the failed stage and pending teardown. The running poller backs off repeated security failures. Domain, device and entity identity remain unchanged.

Validation: 138 tests against HA 2026.10.4, Ruff and mypy. See VALIDATION.md for hardware results and remaining limits. Restart Home Assistant after installing.
