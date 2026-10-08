# Panasonic H&C Bluetooth 0.2.0

The controller core is now separated into typed protocol, state, BLE session, command transactions and supervised polling. Existing domain, device and entity identity remain unchanged.

Fixes include unrelated/partial status handling, stale Eco state after reconnect, total command deadlines, cancellation/late-notification races, unexpected backend write errors and reconnect bookkeeping. Adds a nearby-device picker and connection/route diagnostics. Energy accounting remains removed; Eco control remains supported.

Validation: 106 tests, 91% statement coverage, Ruff and mypy. On a real CZ-RTC6BLW, temperature 25 → 25.5 → 25 °C retained current temperature throughout; all fan speeds, Eco toggling, current cool mode and power-on while already on were confirmed. Fan and Eco restored. No off/on cycling or other physical operating modes tested.

The known local-adapter connection failure remains: HA may select an unsuitable adapter before the bonded proxy. A temporary local-adapter isolation allowed the live test; the adapter was restored. There is no supported per-entry proxy pinning or universal PIN-confirmation wizard in the inspected HA APIs. The README and Bluetooth investigation explain pairing and route selection without claiming these external limitations are solved.

Install through HACS and restart Home Assistant. Keep the existing integration entry. See the [review](https://github.com/rndm2/panasonic_hc_bluetooth/blob/main/docs/REVIEW-0.2.0.md) and [validation record](https://github.com/rndm2/panasonic_hc_bluetooth/blob/main/docs/VALIDATION.md).
