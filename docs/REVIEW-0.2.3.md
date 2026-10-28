# Production cleanup review — 0.2.3

Reconnect now retains the saved status-confirmed Bluetooth source through missing,
busy and failed-readiness states. It does not contact an unknown adapter while its
paired proxy restarts. Both HA selection entry points enforce this constraint.
Initial setup remains able to search routes. The explicit `reset_route` Reconnect
option permits deliberate migration without deleting bonds or entity history.

Tests cover unavailable/busy preferred sources, selection bypass, failed readiness,
route reset versus normal reconnect, unchanged entry data, and missing HA hooks.
Existing lifecycle/security ownership tests remain in place.

Firmware cleanup removes the temporary protected-write node/header and three
manual diagnostic API actions. Native pairing controls, random-address setup,
the IDF key-retention fix and preserve-bonds-on-failure policy remain. INFO logging
still displays deliberately initiated numeric comparison. No HVAC commands or
unrelated network/authentication settings change.

SDK preparation verifies the tested source fingerprint, copies only bt, writes
atomically, records provenance and license, refuses modified output and leaves
shared SDK input unchanged. Tests cover wrong revision, output mutation, partial
copy failure, idempotence and accidental output inside the shared SDK.

152 Python tests plus the extracted real-C bond regression pass locally. Ruff,
formatting, mypy and firmware compilation are required before deployment. Live
validation is recorded in VALIDATION.md. Private HA hooks and the pinned SDK
workaround remain explicit compatibility dependencies, not a multi-day uptime
or cross-model guarantee.
