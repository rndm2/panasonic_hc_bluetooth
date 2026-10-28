# Validation

## 0.2.2 candidate — 2026-10-28

- Environment: HA 2026.10.4, ESPHome 2026.10.1, IDF 5.5.6, CZ-RTC6BLW.
- 140 automated integration tests pass. Ruff lint/format, mypy and whitespace
  checks pass. CI also executes the actual extracted SDK handler as a C regression.
- Confirmed integration fixes: retain live-client ownership after failed teardown,
  block overlapping replacement, allow the backend disconnect/settlement budget,
  preserve authentication errors on link drop and stop fallback from the bonded
  preferred source after such an error. No component pair/unpair calls are made.
- Earlier HA tests lost authentication with a still-present NVS bond, then lost
  that NVS bond after an unanswered SMP timeout. The independent native test below
  isolates an SDK cause. A `Deleting unpaired device` log alone is not proof that
  NVS was deleted.

### Independent firmware reproduction and fix

The HA Panasonic entry remained disabled throughout these native tests.

- Original IDF: after reboot, authentication succeeds (type 1, mode 13) and the
  protected CCCD enable/disable responses both have status 0. After ordinary native
  disconnect/connect, a new comparison code appears and that CCCD write returns
  status 5. NVS still contains the bond before the SMP timeout, then has none.
- SDK root: `smp_check_auth_req()` clears RAM keys on encryption using an existing
  bond. The subsequent session cannot find usable RAM keys. The extracted actual
  C function reproduces this; gating replacement on `SMP_PAIR_FLAG_ENC_AFTER_PAIR`
  preserves reused keys while keeping successful new-pair replacement intact.
- Patched image: after one manual pairing, three consecutive native reconnects
  authenticate without a comparison code. Every protected CCCD enable/disable
  returns status 0, and NVS retains one target bond.
- A second OTA build uses a YAML per-device `bt` component override. A normal
  ESPHome compile succeeds and compile_commands identifies the patched SMP source.
  The shared SDK file SHA256 remains unchanged. After that image's reboot, NVS
  retains the bond, authentication succeeds and both protected writes return 0.
- The target config disables automatic central-role NVS bond removal on pairing
  failure. Encryption, numeric comparison and hardened repairing remain enabled.
- No bootloader, partition table, NVS image or unrelated adapter was flashed.
  The old application image is retained for rollback.

### HA component validation

- Deployed the final transport with a previous-source SHA256 guard. `ha core check`
  passed and HA Core restarted successfully.
- Enabled the existing entry after closing only the native test client. It loaded
  on the intended proxy, authenticated without a new code and returned Panasonic
  status. The existing climate entity reports cool, target/current 24.5 degrees,
  fan auto and eco. No HVAC setting commands were sent in this investigation.
- `panasonic_hc.reconnect` successfully reloaded the same entry, authenticated with
  the existing bond and restored status.
- Restarted only the target proxy with the integration active. The entry recovered
  automatically in approximately 13 seconds. NVS retained one target bond and the
  climate returned valid status/current temperature. One expected outage warning
  recorded attempts through other adapters while the preferred proxy was offline.
- These are bounded reconnect/reboot checks. They do not establish long-term uptime,
  every HVAC command, other controller/SDK versions or physical compressor behavior.

## 0.2.1 — adding after deletion and route fallback

- Reproduced the pre-fix `cannot_connect` through HA's native config-flow API: local GATT connection succeeded but readiness failed while a bonded proxy was available.
- Staged 0.2.1, passed HA configuration check and restarted Core. No adapters or proxies were disabled or restarted.
- The owner then added the deleted controller through the UI and reported it working. Independently verified the new entry is loaded, the original climate entity ID is reused, and status/current temperature are available.
- Saved preferred source matches the bonded proxy. HA connection allocations independently confirm the controller occupies that proxy, with both other adapters still enabled and unused by this controller.
- Manual Panasonic reconnect succeeded and retained the same proxy.
- Updated the existing recovery automation only to resolve its entry ID from the stable climate entity. Checked the template live, verified YAML semantic equality except that field, passed `ha core check` and reloaded automations without running their actions.
- 117 tests, 92% statement coverage; Ruff, formatting, mypy and whitespace checks pass. Tests cover failed notification/status, bounded failure, preferred-source persistence, missing/busy preference and isolation from other BLE clients.
- No new pairing, proxy power-loss test or physical HVAC mode cycling was performed.

## 0.2.0 — architecture rewrite

- 106 tests, 91% statement coverage; Ruff lint/format, mypy and diff checks pass.
- HA configuration check and staging restart completed on HA 2026.10.0.
- Existing entry and climate identity reused; integration diagnostics report version 0.2.0.
- Initial local BlueZ connection failed with `Not connected`. Previously authorized temporary
  local-adapter isolation allowed proxy reconnect; the local adapter was restored immediately.
- Live diagnostics downloaded successfully: ready/connected, zero malformed packets and zero
  rejected temperature samples at that observation; all three candidate routes and slots reported.
- Combined cool/target 25 → 25.5 → 25 °C succeeded. Five scoped event/snapshot samples,
  zero missing current-temperature values; measured current stayed 22.5 °C.
- Nearby-device form rendered through the real HA config-flow API; test flow was aborted.
  That check exposed unnamed MAC-only advertisements cluttering the picker; they are now filtered.
- Recovery automation received only its authorized stale-entry-ID replacement; semantic YAML
  equality verified all other values unchanged, `ha core check` passed and `automation.reload` succeeded.
- Owner clarified that an automation may set 25 °C. This is accepted behavior, not a defect.

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
  an independent ESPHome climate later reported 25 °C. The owner later confirmed that an
  automation may set 25 °C; the short event test proves the flicker fix, not exclusive control.

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

## Historical 0.1.x limits

No test here verifies compressor operation, every HVAC mode, pairing a new proxy, power-loss
failover or other controller models. Manual reconnect does not reset bonds, restart a proxy,
pin a route, or make an unpaired adapter usable. A stronger unpaired adapter can be chosen by HA.
Energy accounting is intentionally absent.

Additional 0.2.0 live command checks: current `cool` mode and power-on while already on,
fan auto → low → medium → high → auto, preset eco → none → eco all succeeded with
matching returned status. Fan and preset were restored. Final observation after those
commands: cool, target 24.5 °C, current 22.5 °C, auto fan, eco. Target changes from other
controllers/automation or preset behavior are reported, not repeatedly overwritten.
Actual off/on cycling and other physical HVAC modes were not exercised.
