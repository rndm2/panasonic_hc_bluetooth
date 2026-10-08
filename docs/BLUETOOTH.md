# Bluetooth selection and pairing investigation — 0.2.0

Inspected the installed Home Assistant 2026.10.0 stack, `habluetooth` wrapper/manager, `bleak-retry-connector` 4.7.1, `bleak-esphome` 4.0.0 and the deployed proxy's BLE configuration.

## Selection

`HaBleakClientWrapper` retains the target address when constructed with a BLEDevice. During `connect()`, it enumerates scanner devices for that address, sorts by RSSI and connection-path score, then chooses a backend with an available slot. The score includes failure history and connection contention. Passing a BLEDevice from one proxy, or refreshing it before reconnect, does not bind the connection to that proxy. The retry connector's declared device callback is not a route-pinning mechanism.

The HA wrapper records connection success before the integration subscribes to Panasonic notifications. Thus an adapter that connects but fails at `start_notify()` can remain preferred; post-connect protocol readiness is not part of that connection-success score. Local BlueZ `NotConnected` failures at this stage were observed in the deployment environment, while connection through the previously bonded ESPHome proxy succeeded.

The installed stack exposes no supported per-entry preferred-source argument. The [HA scanner APIs](https://developers.home-assistant.io/docs/core/bluetooth/api/) allow read-only inspection and explicitly prohibit changing scanner state. This integration therefore does not patch HA internals or disable other integrations to force a route. Diagnostics report candidate paths without identifying data; HA Bluetooth logs report the actual chosen path.

Temporarily disabling the local adapter can isolate a proxy test, but affects other devices and is not an integration-level fix. The local adapter was previously restored after each such authorized test.

## Discovery versus pairing

Discovery finds an advertisement; setup validates the Panasonic service/status; pairing creates a security bond. These are separate operations. A `CZ-RTC6*` name can trigger discovery. The tested renamed controller advertises no identifying service UUID or manufacturer data, so automatic identification from its advertisement is not possible. The 0.2.0 nearby-device picker permits explicit selection without probing unrelated devices automatically.

The integration has no pairing wizard. A proposed wizard would need to select the correct adapter, start the pairing operation, display a request from that exact adapter/controller, accept or reject the matching PIN, handle cancellation/timeouts and release the connection. A generic `pair=True` switch does not implement that flow.

The deployed ESPHome proxy already has `display_yes_no`, a controller-specific BLE client, a numeric-comparison event, a confirmation action and manual connect/disconnect/remove-bond actions. Its BLE client has `auto_connect: false`; the proxy has one active slot. These firmware-specific facilities are distinct from HA's generic Bluetooth client API. No firmware or bonds were changed during this rewrite.

[ESPHome BLE Client](https://esphome.io/components/ble_client/) supports numeric-comparison triggers/replies. [bleak-esphome](https://github.com/Bluetooth-Devices/bleak-esphome) provides pairing when the proxy reports the feature; the inspected proxy API does not by itself supply a generic HA user-facing PIN confirmation flow. Human confirmation on the Panasonic controller remains required. Unattended confirmation is not implemented.
