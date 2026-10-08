# Panasonic H&C Bluetooth 0.1.0

First independently maintained release under `rndm2/panasonic_hc_bluetooth`.
Original implementation: David Collett; maintained and updated by Kostiantyn Marianovskyi (@rndm2).

- Manual **Reconnect Bluetooth** button and `panasonic_hc.reconnect` action.
- Bluetooth route refresh, status timeouts, failed-connection cleanup and safe unload.
- Validated protocol frames and readable configuration/action failures.
- Typed HA runtime data, redacted diagnostics and automated regression checks.
- **Energy tracking removed**, including its BLE traffic.

Requires Home Assistant 2026.10.0 or newer. Install using the new HACS custom repository URL.
Keep the existing Panasonic integration entry: the domain remains `panasonic_hc` and climate
identity remains unchanged. Do not install both upstream and this repository simultaneously.
Old energy history is retained; an old energy entity can remain unavailable in the registry.

Hardware validation status is recorded in `docs/VALIDATION.md`; synthetic tests do not certify
all controller models, proxy failover situations or HVAC command semantics.
