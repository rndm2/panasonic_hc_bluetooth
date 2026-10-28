# Production review — 0.2.2

The 0.2.1 transport assumed that a connected GATT link was ready for protected Panasonic characteristics. Live ESPHome logs showed service discovery followed by CCCD status 5, local disconnect, then authentication failure. OTA/API resets are separate events; the available evidence does not prove the original cause of key loss.

The transport now explicitly awaits Bleak pair() before subscribing or sending status requests. Public backend pairing replaces assumptions about security readiness. Existing keys may be reused; missing keys may require manual confirmation. No automatic numeric-comparison acceptance, bond removal, firmware changes or global adapter manipulation is performed.

Review checks:

- No notification callback or GATT write can run before authentication succeeds.
- Authentication timeout/cancellation cleans the session, releases the controller lock and preserves the appropriate error type.
- Authentication failure of the remembered source does not initiate pairing on other adapters.
- Failed routes retain their reasons. Known exhaustion prevents the extra retry-connector timeout that previously erased the root cause.
- Typed shared errors have one implementation in errors.py. Runtime authentication backoff is bounded and repeated outage warnings are coalesced; HA controls initial setup retry timing.
- Pairing has a separate deadline within a larger total readiness deadline. The backend itself may have a shorter pairing timeout.
- Diagnostics expose stages/counts without raw pairing material or new device identifiers.

Validation: 131 tests passed, 92% coverage, Ruff lint/format, mypy and whitespace checks. The first 129 regressions also passed against HA 2026.10.0; the full suite targets the deployed HA 2026.10.4 with the matching pytest plugin. Hardware validation is recorded separately in VALIDATION.md. Other controller models and uncontrolled long outages remain unverified.
