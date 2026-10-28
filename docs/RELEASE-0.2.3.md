# Panasonic H&C Bluetooth 0.2.3

Keep reconnect on the saved paired adapter/proxy while it is offline or busy,
rather than probing adapters whose pairing is unknown. For deliberate migration,
the Reconnect action adds Search Bluetooth routes again (`reset_route: true`).
Initial setup retains route search. Device/entity identity and existing commands
are unchanged.

Production proxy configuration removes temporary test APIs and the protected-GATT
probe, uses INFO logging with explicit pairing-code visibility, and retains the
IDF 5.5.6 bond-key fix. SDK preparation now produces a fingerprint-checked, atomic
bt-only artifact with provenance and the SDK license.

152 Python tests, the real-C SDK regression, Ruff, formatting and mypy are checked.
See VALIDATION.md for final live checks. HACS installs the integration only;
ESPHome cleanup and its pinned SDK workaround are separate firmware changes.
Review the local bt override before framework upgrades.
