# Cleanup review — 0.2.4

The IDF bond-key fix does not replace connection ownership, asynchronous security
completion or paired-source routing. The integration contains no pair/unpair calls,
SDK-version-specific repair logic or firmware diagnostic API calls. Retain:

- The saved status-confirmed source and both isolated HA route-selection hooks.
- Bounded waits for source readiness and ATT authentication/encryption completion.
- The 30-second backend teardown budget, disconnect lock and retained live-client ownership.
- Hardware-tested notification settling, command serialization and status confirmation.

Remove duplicated pre-disconnects in the polling worker and route-error path.
The transport already closes its predecessor before creating a client. Centralize
connection-failure cleanup and exception translation. Failure handlers skip a
teardown that already failed; the next recovery attempt, explicit reconnect or
shutdown can retry it. Stop route search if cleanup left a live session behind.

The previous code called a failing backend disconnect three times in one connect
attempt. Another regression lost the original notification error while retrying
cleanup/route selection. New tests preserve that cause, enforce one cleanup attempt,
retain ownership, prevent another backend allocation and verify worker backoff.
The existing next-route test now verifies that the old session closes before the
next route is selected. Explicit teardown retry, cancellation, pending security,
manual route reset and normal reconnect tests still pass.

Local validation: 161 tests, 93% coverage, Ruff lint/format, mypy and the actual-C
SDK regression pass. These are local tests with mocked Bluetooth I/O. No HA reload,
proxy restart, deployment or new physical reconnect test was performed for
this release validation.
