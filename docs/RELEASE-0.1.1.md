# Panasonic H&C Bluetooth 0.1.1

Fixes found during critical review and live CZ-RTC6BLW testing:

- Preserve retryable setup failures when BlueZ disconnect cleanup raises an assertion.
- Clean up unexpected initialization errors and ignore queued notifications from old connections.
- Keep diagnostics usable before successful setup and expose the underlying setup error.
- Wait for delayed command confirmation; resend status requests, never the HVAC command.
- Wake recovery when the command deadline expires without a status reply.
- Correct documentation: Home Assistant selects the BLE backend; reconnect does not pin a proxy.

Validation: 70 tests, Ruff, formatting, mypy, HACS and hassfest. On HA 2026.10.0 with an active
ESPHome proxy, setup, manual reconnect and automatic setup after restart succeeded. Temperature,
fan and eco changes were confirmed and restored. See [VALIDATION.md](VALIDATION.md) for limits.

The domain remains `panasonic_hc`; climate identity is preserved. Energy accounting remains
removed. Published 0.1.0 is unchanged. Update in HACS and restart Home Assistant.
