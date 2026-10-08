# Production review — 0.1.2

Reviewed transport, protocol, state merging, HA lifecycle, climate/button actions, config flow,
diagnostics, manifest, translations, tests and CI. No complete rewrite was needed.

| Finding | Severity | Resolution |
| --- | --- | --- |
| Partial status replaced a valid current temperature with unknown | P1 | Preserve separately timed last valid measurement |
| First rejected temperature erased the validation anchor; repeated bad value was accepted | P1 | Independent anchor survives rejection and expiry |
| Preserving a reading indefinitely would create stale data | P2 | Ten-minute expiry timer; partial packets do not renew it; disconnect clears it |
| Combined temperature action ignored HVAC mode | P2 | Validate first, serialize all commands, confirm temperature and mode |
| Command callers could wait indefinitely behind slow operations | P2 | Five-second queue deadline; never steal another operation's lock |
| Disabled entry reload could report successful reconnect | P2 | Explicit validation error |
| Unexpected backend exception could permanently terminate the poll worker | P2 | Supervised retry with traceback and cancellation propagation |
| All command errors looked like confirmation failures | P2 | Include actual operation failure reason |

Regression tests cover partial/full/partial packet sequences, repeated rejected readings,
freshness boundary, timer expiry without new packets, timer cleanup, combined actions,
queue timeout/cancellation, disabled reconnect and poll-worker recovery.

## Deliberately not claimed solved

- HA chooses the connection route. Pairing and route-specific failures are not distinguishable
  from every generic backend error; deterministic proxy pinning is not implemented.
- Discovery currently matches `CZ-RTC6*`. A renamed device advertising no identifying UUID or
  manufacturer data cannot be reliably identified as Panasonic from advertisements alone.
  A user-selected nearby-device list with a targeted probe is a suitable future fallback.
- Bleak/ESPHome can initiate pairing on supported firmware. Numeric-comparison confirmation
  still requires user/controller interaction and proxy support; no unattended pairing is added.
- No fresh raw-wire capture proves the meaning of every temperature variant. The existing
  range/jump checks remain heuristics; a preserved reading expires rather than becoming a guess.
- Complete HVAC mode transitions, physical compressor behavior and proxy power loss are not tested.
- A future state/transport separation would help; a full rewrite would discard verified wire behavior.
