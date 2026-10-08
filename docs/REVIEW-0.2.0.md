# Production review — 0.2.0

Scope: every integration module, HA lifecycle/configuration/entity interfaces, protocol command bytes, tests, metadata, CI, README and deployment behavior. The user subsequently requested the architecture rewrite that 0.1.2's review had deferred. Historical review files describe their original release.

## Changes and regression evidence

| Finding | Fix / evidence |
| --- | --- |
| Protocol, state freshness and BLE lifecycle shared a mutable monolith | Immutable typed codec, separate clock-free state model, BLE transport, transactions and supervised runtime |
| A request or unrelated parcel sharing the status identifier could be mistaken for state | Validate indoor-to-app response/notification headers before status decoding; request/ack/wrong-source tests |
| One valid status in a malformed multi-packet frame could be partially applied | Decode all reports before applying any; atomic-frame regression |
| Invalid setpoints from wire could enter climate state | Validate status target range; malformed-input tests |
| Optional Eco state survived reconnect into a short status | Reset session-scoped optional state; reconnect regression |
| Command timeout excluded preceding writes | Bound the entire transaction; hung-write regression, including intervening notification |
| Cancellation after a write could leave the session trusted | Invalidate readiness and notification acceptance; active-cancellation regression |
| Late packets could revive a failed session | Session identity plus notification-acceptance guard; late-notification regression |
| Unexpected write-backend errors escaped HA's action error handling | Translate failures and invalidate readiness; RuntimeError regression |
| Repeated connect could create another client | Serialized idempotent connect; duplicate-client regression |
| Reconnect kept a lock object for every historical entry | Track only in-flight IDs and remove in finally; cancellation/retry regression |
| Renamed devices were inconvenient to add | Explicit nearby-device picker plus custom MAC, excluding configured devices and unnamed address-only advertisements |
| Diagnostics could not explain readiness or candidate routes | Counters, ages, stage and read-only route/slot diagnostics; privacy regression |
| Recovery automation referenced a removed entry | Separately authorized exact ID correction; semantic YAML comparison, HA config check and automation reload |

Retained wire behavior: power 2/3, mode-6 auto alias, half-degree temperature fields 9/10, all five fan fields 17–21, Eco 9/11, status request payload and UART keepalive. Literal golden frames protect power/temperature compatibility. Energy accounting remains absent. Unused outdoor/outing application classes were removed; unknown packets remain structurally decodable and do not update climate state.

## Validation

Local checks: 106 tests, 91% statement coverage, Ruff lint/format, mypy and whitespace validation. Hardware results are recorded separately in `VALIDATION.md`; mock tests do not prove physical operation.

## Boundaries remaining

- HA route choice and bonding across different adapters are external to the integration; no supported route pinning or universal pairing wizard was found. See `BLUETOOTH.md`.
- Temperature range/jump validation is heuristic. An initial plausible but incorrect vendor-variant value cannot be detected reliably without protocol evidence; sustained jumps over 20 °C are rejected until a valid nearby sample or a new session. Expired values are unknown, never silently refreshed.
- The protocol has no implemented request IDs. Confirmation means a fresh matching received status, not proof that no automation/other controller can immediately change it again. The owner confirmed that a target of 25 °C may be set by automation and is valid.
- No claim that every possible defect or controller variant is eliminated. Full physical mode transitions, prolonged proxy outage, new pairing and other controller models remain hardware validation tasks.
- Upstream license permission remains unresolved; attribution does not resolve it.
