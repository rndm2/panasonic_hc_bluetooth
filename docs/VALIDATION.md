# Validation

## 0.1.2 — temperature state and action review

- 83 automated tests pass; Ruff, formatting, mypy, HACS and hassfest pass.
- On the real CZ-RTC6BLW, subscribed to HA state_changed events before changing the target.
- Combined target/mode command: 24.5 → 25 °C with cool; then restored target to 24.5 °C.
- Both actions succeeded; five event/snapshot samples contained zero unknown current-temperature
  readings. Actual current measurement updated from 24.5 to 24.0 °C without disappearing.
- After startup, the existing BlueZ route failure recurred. Temporarily disabling the local
  adapter allowed proxy reconnect; the local adapter was restored before the temperature test.
- Synthetic tests verify ten-minute freshness expiry, no timer leaks, repeated rejected
  readings, queue timeout/cancellation, combined off/mode actions and disabled-entry reconnect.
- Hardware test does not prove every packet variant, all mode transitions or proxy failover.
- Follow-up observation: after accepting a restored 24.5 °C target, both this integration and
  an independent ESPHome climate later reported 25 °C. The cause was not isolated; the short
  event test proves the flicker fix, not long-term target persistence or absence of other control.

## Historical 0.1.1 validation

## Automated

- Python 3.14.6 / Home Assistant 2026.10.0.
- 70 passing tests covering packet framing, malformed inputs, MAC validation, original wire
  commands, optional status fields, cleanup/cancellation, unload, stable identity, reconnect
  service behavior, late notifications and diagnostics before successful setup.
- Ruff, formatting, mypy and `git diff --check` pass.
- GitHub PR checks include pytest, HACS and hassfest. HACS excludes only the license check
  because upstream supplied no license grant.
- Status polling tests verify that no energy consumption requests are sent.
- Mocked device lookup tests do not establish physical proxy failover.

## Live controller — 2026-10-08

- Home Assistant 2026.10.0, CZ-RTC6BLW, active ESPHome Bluetooth proxy.
- The original config entry had been removed before this validation. A replacement entry
  was added through HA's normal configuration flow for the same controller address.
- Existing climate entity ID and unique ID were reused; no duplicate climate entity was created.
- Valid status received: cool, target/current 24.5 °C, auto fan, eco preset.
- Re-sending the current temperature, fan and preset completed with matching status replies.
- Automatic backend selection initially chose an unusable local adapter. Temporarily disabling
  that adapter allowed setup through the bonded proxy; the adapter was then re-enabled.
- Manual reconnect through the device button succeeded after the local adapter was re-enabled.
- A real 24.5 → 25 °C target change exposed premature confirmation failure; subsequent status
  confirmed 25 °C. The target was restored to 24.5 °C. A deadline-based confirmation fix and
  regression test were added. After deploying the confirmation fix and restarting HA,
  24.5 → 25 → 24.5 °C completed successfully with matching returned status.
- Auto → low → auto fan and eco → none → eco preset completed successfully.
- Automatic setup after HA restart succeeded with all adapters enabled. On the last
  HACS-required restart, initial setup and one manual attempt failed; a subsequent automatic
  retry restored the connection. First-attempt success and seamless startup are not guaranteed.
- Some short/ambiguous status variants report unknown current temperature; target-temperature
  confirmation is independent of that measurement. No guessed measurement is published.

## Remaining limits

No test here verifies compressor operation, every HVAC mode, pairing a new proxy, power-loss
failover or other controller models. Manual reconnect does not reset bonds, restart a proxy,
pin a route, or make an unpaired adapter usable. A stronger unpaired adapter can be chosen by HA.
Energy accounting is intentionally absent.
