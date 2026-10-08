# Audit and migration record

Baseline: `a8859172df5238573b40f45e8d045165a568e7a1`, all 13 tracked files reviewed.
The separate maintainer branch `dd32fb93f691455d7571190f515af1f1bdd76924` was also
reviewed and merged, preserving original commit attribution.

| Original file | Resolution |
| --- | --- |
| `__init__.py` | Typed runtime data, first valid status, retry/backoff and deterministic unload |
| `climate.py` | Confirmed state properties, explicit turn-on/off, surfaced action failures |
| `config_flow.py` | Strict MAC validation, connection check, HA 2026.10 probatio schema |
| `const.py` | Preserve domain/model identity; remove unused dispatcher constants |
| `manifest.json` | Maintainer, URLs, Bluetooth dependency, direct retry-connector requirement, version |
| `panasonic_hc.py` | Cleanup, status timeouts, serialized transactions, explicit manual reconnect |
| `panasonic_hc_proto.py` | Length/checksum/header validation, short status, outdoor constructor, keepalive, auto alias, fan fields |
| `sensor.py` | Removed together with all energy tracking by maintainer request |
| `strings.json` | Configuration and action errors; unused confirm step removed |
| `translations/en.json` | Same keys/messages as source strings |
| `README.md` | Attribution, installation, migration, limitations, diagnostics, pairing caveats |
| `hacs.json` | Display name and tested minimum HA version |
| `.github/workflows/validate.yaml` | Tests, lint, formatting, typing, HACS and hassfest |

New modules `entity.py` and `diagnostics.py` remove duplicated lifecycle code and expose
non-identifying diagnostic state. `button.py` and `services.yaml` expose manual reconnect. Tests isolate BLE; synthetic packet tests are not physical evidence.

The original 0.5-second connection/notification settling delays are retained; timeout-based
response handling does not assume that the controller can subscribe immediately after connect.

## Remaining hardware checks

- Confirm mode, fan and eco status replies and optional-field semantics on the actual controller.
- Check valid temperature packet variants; unexplained jumps are reported unknown rather than frozen.
- Confirm proxy reconnection and controller restart recovery.
- Energy scope was explicitly removed; no energy requests or sensor remain.
- Record safe packet fixtures before extending support beyond the known controller model.
- Clarify the upstream license; no new license is asserted for inherited code.
