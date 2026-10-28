# Bluetooth selection and pairing investigation — 0.2.1

Inspected the installed Home Assistant 2026.10.0 stack, `habluetooth` wrapper/manager, `bleak-retry-connector` 4.7.1, `bleak-esphome` 4.0.0 and the deployed proxy's BLE configuration.

## Selection

`HaBleakClientWrapper` retains the target address when constructed with a BLEDevice. During `connect()`, it enumerates scanner devices for that address, sorts by RSSI and connection-path score, then chooses a backend with an available slot. The score includes failure history and connection contention. Passing a BLEDevice from one proxy, or refreshing it before reconnect, does not bind the connection to that proxy. The retry connector's declared device callback is not a route-pinning mechanism.

The HA wrapper records connection success before the integration subscribes to Panasonic notifications. Thus an adapter that connects but fails at `start_notify()` can remain preferred; post-connect protocol readiness is not part of that connection-success score. Local BlueZ `NotConnected` failures at this stage were observed in the deployment environment, while connection through the previously bonded ESPHome proxy succeeded.

There is no public preferred-source constructor parameter in the inspected wrapper. That is not the same as there being no implementation path: the earlier conclusion that the integration could not recover without adapter isolation was too strong.

Version 0.2.1 subclasses `HaBleakClientWrapper` only for Panasonic. Two isolated protected selection hooks prefer the last status-confirmed source and skip sources that failed the current handshake. The inherited HA connect/disconnect code still chooses backend implementations, allocates local slots, tracks remote connections and handles scanner removal. It changes no shared scanner properties or route scores and does not disable anything. Read-only route enumeration uses the manager already passed to HA's selection hook.

After GATT, notify or status failure, the controller closes its own failed client and tries another source. No HVAC command is replayed during route search. Only a complete status handshake updates the preference. Config flow persists it before entry setup, avoiding immediately switching back to the bad path after validation disconnects. Existing entries learn a working preference during successful setup; failure exclusions reset for the next connection attempt.

The compatibility adapter relies on protected HA Bluetooth methods and is regression-tested against the installed HA 2026.10.0 wrapper. Future HA updates need to retain or adapt these hooks. This tradeoff is explicit; it is not a claim that a new public HA pinning API exists.

Earlier temporary adapter-isolation tests were diagnostic workarounds. The owner has revoked permission to disable adapters/proxies, and the 0.2.1 fix and validation do not use them.

## Discovery versus pairing

Discovery finds an advertisement; setup validates the Panasonic service/status; pairing creates a security bond. These are separate operations. A `CZ-RTC6*` name can trigger discovery. The tested renamed controller advertises no identifying service UUID or manufacturer data, so automatic identification from its advertisement is not possible. The 0.2.0 nearby-device picker permits explicit selection without probing unrelated devices automatically.

The integration has no pairing wizard. A proposed wizard would need to select the correct adapter, start the pairing operation, display a request from that exact adapter/controller, accept or reject the matching PIN, handle cancellation/timeouts and release the connection. A generic `pair=True` switch does not implement that flow.

The deployed ESPHome proxy already has `display_yes_no`, a controller-specific BLE client, a numeric-comparison event, a confirmation action and manual connect/disconnect/remove-bond actions. Its BLE client has `auto_connect: false`; the proxy has one active slot. These firmware-specific facilities are distinct from HA's generic Bluetooth client API. No firmware or bonds were changed during this rewrite.

[ESPHome BLE Client](https://esphome.io/components/ble_client/) supports numeric-comparison triggers/replies. [bleak-esphome](https://github.com/Bluetooth-Devices/bleak-esphome) provides pairing when the proxy reports the feature; the inspected proxy API does not by itself supply a generic HA user-facing PIN confirmation flow. Human confirmation on the Panasonic controller remains required. Unattended confirmation is not implemented.


## 0.2.2: session ownership and protected notifications

The initial 0.2.1 path disconnected immediately on an unauthenticated CCCD write. An early 0.2.2 experiment forced pair() on every reconnect; this did not solve the reported bond loss and was removed. The owner independently demonstrated a direct proxy connection and preserved bond after reboot with only one pairing confirmation.

The corrected transport lets the controller finish authentication on the same link. It retries notification subscription only for ATT insufficient authentication/encryption, with a bounded 60-second deadline. It never calls pair()/unpair() or accepts a comparison code. Non-security errors fail normally. A remembered source's authentication failure is reported without trying to re-pair through other adapters.

A confirmed lifecycle defect was the 10-second cleanup deadline versus ESPHome's 20-second disconnect response and 5-second settlement budgets. Cleanup also dropped its client reference before knowing whether the link had closed. The corrected transport allows 30 seconds, retains a still-connected client on failure, serializes disconnect calls, and blocks replacement clients. Setup keeps runtime ownership even when it fails, unload reports failed teardown, and config-flow retries retain their pending validation controller.

Known exhausted routes stop immediately instead of burning another selection timeout. Error summaries preserve the individual causes. Diagnostics expose the failed stage and pending teardown without keys or raw frames. The running worker coalesces outage logs and backs off security failures; HA owns initial setup scheduling.

Temporary proxy diagnostics report only bond metadata. The manual proxy client needed its known static-random peer address type set correctly. The diagnostic firmware has no automatic confirmation or bond removal. SDK/build inspection confirmed bonding storage is enabled; current key presence was measured rather than inferred from an auth-success log.


## Production recovery from 0.2.3

The saved source identifies the adapter/proxy whose Panasonic handshake actually
succeeded. It is retained while that source is missing or busy and on readiness
failure. Automatic reconnect never probes an unknown source after one is saved.
Initial setup and the explicit `reset_route: true` Reconnect action retain the
route search. Both private HA selection hooks are checked before allocating slots.
The reset changes routing metadata only and does not pair/unpair or change entity
identity. Unrelated Bluetooth adapters stay enabled.
