# Production review — 0.2.1

## Regression and repair

The stricter configuration flow introduced a regression: a single failed HA-selected BLE route rejected a controller reachable through another proxy. Passing a proxy BLEDevice did not pin the actual connection. Local GATT connection could succeed while notification subscription failed, so the local route could keep scoring well.

The controller now searches other routes after GATT, notification or initial status failure. A per-client policy excludes failed sources only during this search. A status-confirmed source is preferred on reconnect and persisted by config flow/setup. The inherited HA wrapper still handles backend creation, slots, connection tracking and scanner removal. No shared classes, scanner properties, adapter enablement or pairing bonds are modified.

## Review findings and evidence

- Keeping preference only in the validation object would lose it before entry setup: persist the successful source in entry data, and restore it during setup.
- A successful GATT connection is insufficient: require a valid controller status before marking the route successful.
- Repeated failures must terminate: one search has a 90-second deadline, plus bounded cleanup; exhausted candidates return a normal flow/setup error.
- Failed and cancelled attempts retain the existing disconnect and late-notification guards. A command is not replayed as part of route search.
- A preference must not prevent recovery: missing/busy/failed preferred paths fall back to remaining candidates.
- Route policy must not affect other clients: tests exercise the real installed HA selection hooks with isolated policies and assert no slot allocation for excluded routes.
- Recovery automation contained the deleted entry ID: its separately deployed data now resolves the entry through the stable climate entity ID. No automation action was triggered during this change.

117 tests pass, with 92% statement coverage; Ruff, formatting, mypy and whitespace checks pass. Hardware setup and reconnect results are in VALIDATION.md.

## Compatibility boundaries

The two protected HA wrapper hooks are an intentional compatibility dependency, isolated in connection.py and tested against HA 2026.10.0. They must be reviewed on HA Bluetooth upgrades. This is not a new public HA route-selection API or automatic pairing implementation. A route still needs valid existing security/bonding where the controller requires it. Extended outages and other controller models remain unverified.

A background fallback updates the running controller's preference; config flow and successful entry setup persist it. The preference is a hint and never disables other paths. Historical 0.2.0 documentation describes its original limitation, superseded here.
