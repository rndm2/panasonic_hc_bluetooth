# Validation — 0.1.1

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
  regression test were added; final deployment validation follows before release.

## Remaining limits

No test here verifies compressor operation, every HVAC mode, pairing a new proxy, power-loss
failover or other controller models. Manual reconnect does not reset bonds, restart a proxy,
pin a route, or make an unpaired adapter usable. A stronger unpaired adapter can be chosen by HA.
Energy accounting is intentionally absent.
