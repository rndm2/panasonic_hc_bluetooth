# Production review — 0.2.2

The corrected change addresses ownership and timing of BLE sessions. Earlier forced-pairing experiments did not resolve the reported loss and are not in the final transport. An independent native ESPHome client subsequently reproduced bond loss and isolated an additional SDK defect.

Review findings and regressions:

- A failed disconnect discarded the live client. A new connection could start while its predecessor was still closing. Three new regressions failed against the previous code and pass after the lifecycle fix.
- The 10-second cleanup timeout undercut the installed ESPHome backend's 20-second disconnect response plus 5-second settlement. Cleanup now allows 30 seconds and preserves ownership if the link remains live.
- Unconditional pair() was an unproven experiment and was removed. ESPHome implements it as a request for encryption, which can reuse an existing bond. Calling it is not evidence that a fresh pairing or bond deletion was forced. Security-related notification failures now wait and retry on the same session.
- Failed initial setup lost ownership between retries. Runtime is now retained before connect, and the next setup must close its predecessor before replacement.
- Unload must not report success while the transport still owns a live link. Flow validation likewise retains pending cleanup between retries.
- Exceptions retain their route and non-empty causes. Known candidate exhaustion avoids the extra empty timeout. Expected security failures use dedicated UI messages and worker backoff.

140 tests pass against HA 2026.10.4. Coverage, Ruff and mypy are checked separately before release. The tests include wrapped ATT errors, timeout/cancellation, same-session subscription retries, concurrent teardown/connect, failed setup/flow/unload, no automatic pair/unpair, stable identities and existing command behavior.

Hardware validation is recorded in VALIDATION.md. The private HA route-selection hooks remain a compatibility dependency. A valid GATT connection or authentication log alone does not prove persistent bonding, successful Panasonic status exchange or physical compressor behavior.

Additional firmware finding: the actual IDF 5.5.6 encryption-complete handler
clears RAM keys even on bond reuse. The independent native client passed protected
CCCD access after reboot, then failed the next ordinary reconnect while NVS still
held the bond. The extracted real C handler reproduces the loss. Gating key
replacement on `SMP_PAIR_FLAG_ENC_AFTER_PAIR` fixes that handler regression. The
patched native client then passed three consecutive authenticated reconnects
and protected CCCD enable/disable operations without a new pairing code. This
firmware fix is separate from the integration's confirmed ownership fixes.
See `tools/proxy_security/` for the patch, test, attribution and per-device build
configuration. Final HA/reboot results belong in VALIDATION.md.
