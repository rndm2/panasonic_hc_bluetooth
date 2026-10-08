# Panasonic H&C Bluetooth

Local Home Assistant control of Panasonic CZ-RTC6BLW wired AC controllers through Bluetooth or an active ESPHome proxy. No cloud account is required.

Maintained by [Kostiantyn Marianovskyi (@rndm2)](https://github.com/rndm2). Originally written by [David Collett (@david-collett)](https://github.com/david-collett), based on [david-collett/panasonic_hc](https://github.com/david-collett/panasonic_hc) at `a8859172df5238573b40f45e8d045165a568e7a1`. Original history and the maintainer's earlier `bugfix/index-out-of-range-fix` changes are preserved.

## Requirements and installation

- Home Assistant **2026.10.0+**, tested with 2026.10.0 and Python 3.14.
- A connectable local Bluetooth adapter or active ESPHome Bluetooth proxy.
- The controller must be paired with the adapter/proxy that connects to it.
- CZ-RTC6BLW is the tested model. Other `CZ-RTC6*` models are not verified.

In HACS, add `https://github.com/rndm2/panasonic_hc_bluetooth` as an **Integration** custom repository, install it, and restart HA. Then open **Settings → Devices & services → Add integration → Panasonic H&C Bluetooth**.

Select the controller from nearby Bluetooth devices or enter its colon-separated MAC address. The list can include non-Panasonic devices; choose your controller. Setup validates its Panasonic GATT connection and status before creating an entry. Devices advertising `CZ-RTC6*` also support automatic discovery. A renamed device without identifying service/manufacturer data cannot be automatically classified as Panasonic.

**This setup form is not a Bluetooth pairing wizard.** It validates an existing connection; it does not create a bond or confirm a PIN.

### Migration

The internal domain and directory remain **`panasonic_hc`**. Device identity, climate unique ID, reconnect-button unique ID and existing history are retained. Version 0.2.1 adds only the last working Bluetooth source to entry data; existing identities remain unchanged.

When switching from the original repository, replace its HACS installation with this repository before restarting. Keep the existing integration entry and entities in HA. Two integrations using this domain cannot be installed simultaneously. To roll back, reinstall a previous release and restart.

## Controls and state

Supported: power, heat/cool/auto/dry/fan-only, temperature **16–32 °C in 0.5 °C steps**, fan auto/low/medium/high, and eco preset. The model-specific temperature limits and every physical operating mode have not been exhaustively hardware-tested.

Commands are serialized. They wait up to five seconds for the operation slot, then have a **15-second total transaction deadline**, including writes and confirmation polls. Writes are sent once; a matching received status confirms the requested setting. Stale replies are polled again without resending the command. Combined mode/temperature requests validate all inputs first. A failed multi-write action may have partially affected the controller; read its current state before retrying.

Current temperature is tracked independently. Partial or implausible reports retain the previous valid measurement without refreshing its age. It expires after ten minutes and clears on disconnection. The range/jump filter remains a heuristic because the full vendor protocol is not published; this is not a guarantee about every packet variant. Heating/cooling action is not inferred from room temperature.

Status is polled every 60 seconds while on and 300 seconds while off; notifications also update it. Connection recovery backs off from 5 to 300 seconds. Automations, the wired controller or another integration may legitimately change settings after a command was confirmed.

There is **no energy accounting**: no Daily Energy sensor, consumption polling, parser or snapshots. Eco remains an AC control. Old energy entities may remain unavailable in HA's registry; their historical Recorder data is not deleted.

## Reconnect and adapter selection

Press **Reconnect Bluetooth** on the device, or call the `panasonic_hc.reconnect` action and select its integration entry. The action works during setup retries even when the button is unavailable. It reloads only that entry, cancels its worker, closes the old session and requires fresh controller status. It does not restart proxies, change AC settings or remove bonds. Disabled entries and simultaneous reconnect requests are rejected explicitly.

HA normally selects the connection path using signal strength, failure history and free slots. A GATT connection can succeed while the Panasonic notification/status handshake fails, so HA's normal scoring alone can repeatedly choose a non-working adapter.

From **0.2.1**, the Panasonic client tries another available route when connection, notification subscription or the first valid status fails. Failed sources are excluded only for that controller's current connection attempt. Other Bluetooth devices and adapters remain enabled and unchanged. Each route has bounded connection time and the readiness search has a 90-second deadline, followed by bounded cleanup; exhausted routes return a setup/flow error.

A route is remembered only after a valid status reply. The setup flow saves that source in the integration entry; subsequent setup/reconnect prefers it and falls back if it is missing, busy or fails. This preserves strict validation in the UI without treating one failed adapter as proof that the controller is unreachable.

This uses a small, isolated subclass of HA's Bluetooth client and its protected route-selection hooks, tested against HA 2026.10.0. It retains HA's slot accounting and connection lifecycle; it does not monkeypatch shared classes, alter scanner scores, disable adapters or restart proxies. These protected hooks are a compatibility dependency to review on HA upgrades. See [Bluetooth investigation](docs/BLUETOOTH.md).

## Pairing

Pairing is a separate security exchange between the Panasonic controller and a **particular** Bluetooth adapter/proxy. A bond on one proxy does not pair the other adapters. Numeric comparison requires comparing the PIN and confirming it on the controller and the connecting side.

For a local adapter, use a BlueZ agent such as `bluetoothctl` on the machine owning that adapter: scan, select the controller, pair, compare/confirm the displayed PIN, trust it, then disconnect so HA can take over. Exact access depends on the HA installation type.

For ESPHome, follow the official [BLE Client numeric-comparison documentation](https://esphome.io/components/ble_client/) and [Bluetooth proxy requirements](https://esphome.io/components/bluetooth_proxy/). Firmware must support the pairing interaction. An established Panasonic configuration uses `esp32_ble.io_capability: display_yes_no`, a `ble_client` with `auto_connect: false`, `on_numeric_comparison_request`, and a deliberately invoked `ble_client.numeric_comparison_reply` action. Verify the PIN before accepting it. Do not blindly accept unsolicited requests or keep a firmware BLE client connected while HA needs the proxy slot.

Bleak/ESPHome support a pairing request on capable firmware, but that alone is not a universal HA PIN-confirmation flow. This integration does not initiate unattended pairing, remove bonds, flash ESPHome firmware or invoke custom proxy pairing services.

## Diagnostics

Download diagnostics from the integration page for connection stage, attempts, malformed packets, rejected temperature samples, failed commands, measurement ages and route candidates (RSSI/failures/free slots). MAC addresses, scanner names and raw frames are omitted. Candidate routes are not proof of the currently connected route; inspect HA Bluetooth logs for the actual selection.

If unavailable, check pairing on the selected adapter, active proxy slots, range, and competing clients. Debug logging for `custom_components.panasonic_hc` reports invalid-frame reasons. Manual reconnect cannot fix an offline proxy or missing bond.

## Development and validation

The implementation separates `protocol.py` (immutable frames and command encoding), `state.py` (measurement merging), `transport.py` (BLE session), `panasonic_hc.py` (transactions) and `runtime.py` (poll/recovery supervision). HA entities and config flow are thin adapters. Unknown packet types remain structurally decodable; only supported indoor response/notification status updates climate state.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install '.[test]'
ruff check .
ruff format --check .
mypy
pytest -q --cov=custom_components.panasonic_hc --cov-report=term-missing
```

Tests use synthetic frames and mocked BLE against real HA classes; they do not operate hardware. See [changelog](CHANGELOG.md), [0.2.1 review](docs/REVIEW-0.2.1.md) and [validation](docs/VALIDATION.md) for evidence and remaining boundaries.

## Attribution and licensing

The upstream snapshot contains **no license grant**. Original authorship and history are retained; this repository does not claim ownership of upstream work or invent a license for it. Attribution alone is not a grant of redistribution rights. HACS CI excludes the license check for this custom repository; this does not establish eligibility for the default HACS catalog.
