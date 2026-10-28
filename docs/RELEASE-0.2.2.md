# Panasonic H&C Bluetooth 0.2.2

Fixes reconnect attempts accessing protected Panasonic characteristics before BLE authentication completes. Each session now explicitly authenticates using Bleak pair() before notification subscription and status exchange. A missing/invalid bond may still require comparing and confirming a pairing code on the controller and adapter/proxy controls.

Connection, authentication and readiness have bounded deadlines. Route errors retain their original causes; exhausted routes no longer burn another selection timeout. Authentication failure on the remembered peer is surfaced directly, with a dedicated configuration-flow message. The running poller backs off authentication retries and logs an outage once.

The integration does not automatically accept pairing codes, request bond removal, disable adapters or restart proxies. Existing domain and entity identity remain unchanged. Firmware changes are not required by this release.

Validation: 131 tests, 92% coverage, Ruff and mypy. See VALIDATION.md for hardware results and limits. Restart Home Assistant after installing.
