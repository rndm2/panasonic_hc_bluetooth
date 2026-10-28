# Panasonic H&C Bluetooth 0.2.2

Fixes BLE session ownership during reconnect: failed cleanup keeps the old client, and new setup/reconnect attempts wait for teardown instead of creating overlapping sessions. The disconnect deadline now covers ESPHome's response and slot-settlement budgets.

Protected notification errors wait for authentication on the existing connection. The integration does not initiate pair()/unpair(), accept a comparison code or restart proxies. A bond must already exist on the selected adapter or proxy.

Route errors retain their original causes, known exhaustion returns promptly, and diagnostics report the failed stage and pending teardown. The running poller backs off repeated security failures. Domain, device and entity identity remain unchanged.

Validation: 140 tests against HA 2026.10.4, Ruff and mypy. See VALIDATION.md for hardware results and remaining limits. Restart Home Assistant after installing.


Independent firmware investigation reproduced a separate ESP-IDF 5.5.6 defect:
reusing a bond cleared RAM keys and the next connection requested pairing again.
The repository includes the narrowly scoped SDK patch, actual C regression,
native protected-GATT probe and per-device YAML build instructions. The target
proxy passed three authenticated native reconnects, protected writes after an OTA
reboot, HA manual reconnect and automatic recovery after a proxy reboot.

**Updating this HACS integration does not flash ESPHome or fix that SDK defect.**
The firmware workaround is a separate, explicit build/deploy step documented in
`tools/proxy_security/README.md`. It is pinned to IDF 5.5.6 and must be reviewed
before framework upgrades. No long-term uptime or other hardware is claimed.
