# Production review — 0.2.2

The corrected change addresses ownership and timing of BLE sessions. Earlier forced-pairing experiments did not resolve the reported loss and are not in the final transport. Direct proxy tests provided the comparison case.

Review findings and regressions:

- A failed disconnect discarded the live client. A new connection could start while its predecessor was still closing. Three new regressions failed against the previous code and pass after the lifecycle fix.
- The 10-second cleanup timeout undercut the installed ESPHome backend's 20-second disconnect response plus 5-second settlement. Cleanup now allows 30 seconds and preserves ownership if the link remains live.
- Unconditional pair() was an unproven experiment and was removed to match the observed native reconnect behavior. Its causal role in the bond loss is not established. Security-related notification failures now wait and retry on the same session.
- Failed initial setup lost ownership between retries. Runtime is now retained before connect, and the next setup must close its predecessor before replacement.
- Unload must not report success while the transport still owns a live link. Flow validation likewise retains pending cleanup between retries.
- Exceptions retain their route and non-empty causes. Known candidate exhaustion avoids the extra empty timeout. Expected security failures use dedicated UI messages and worker backoff.

140 tests pass against HA 2026.10.4. Coverage, Ruff and mypy are checked separately before release. The tests include wrapped ATT errors, timeout/cancellation, same-session subscription retries, concurrent teardown/connect, failed setup/flow/unload, no automatic pair/unpair, stable identities and existing command behavior.

Hardware validation is recorded in VALIDATION.md. The private HA route-selection hooks remain a compatibility dependency. A valid GATT connection or authentication log alone does not prove persistent bonding, successful Panasonic status exchange or physical compressor behavior.
