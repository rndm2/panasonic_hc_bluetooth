# Validation — 0.1.0

## Automated

- Python 3.14.6 / Home Assistant 2026.10.0.
- 63 passing tests: valid/invalid MAC, protocol framing, malformed packets, original wire
  command compatibility, optional fields, setup/cleanup/unload, confirmed command failures,
  stable climate identity, manual reconnect, concurrent request rejection and proxy route refresh.
- Ruff, formatting, mypy and `git diff --check` pass.
- HACS custom-repository CI excludes only the license check because upstream supplied no license.
- Energy removal test verifies that status polling sends no consumption requests.

## Live controller

Baseline before installation: existing entity `climate.airiron_thermostat_bluetooth` is
available on the original 0.0.1 integration. Updated installation and manual reconnect
verification are pending. No synthetic test is evidence of physical HVAC behavior.

## Remaining limits

All HVAC modes, physical compressor/fan behavior, pairing on a different proxy, proxy power-loss
failover and model-specific temperature limits need separate hardware verification. The reconnect
action does not reset bonding, restart a proxy or guarantee that a different proxy has a valid bond.
