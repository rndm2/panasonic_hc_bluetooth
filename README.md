# Panasonic H&C Bluetooth

Local Bluetooth control of Panasonic H&C wired air-conditioning controllers in Home Assistant.

Maintained by [Kostiantyn Marianovskyi (@rndm2)](https://github.com/rndm2).
Originally created by [David Collett (@david-collett)](https://github.com/david-collett).
Based on [david-collett/panasonic_hc](https://github.com/david-collett/panasonic_hc),
commit `a8859172df5238573b40f45e8d045165a568e7a1`, with the maintainer's earlier
`bugfix/index-out-of-range-fix` changes preserved in Git history.

## Compatibility

- Home Assistant **2026.10.0 or newer**; tested with 2026.10.0 / Python 3.14.
- Verified controller model from the original integration: **CZ-RTC6BLW**.
  Other `CZ-RTC6*` advertisements may be discovered, but model compatibility is unverified.
- A connectable local Bluetooth adapter or ESPHome active Bluetooth proxy, already paired
  with the controller. No Panasonic cloud account is needed.
- Domain and installation directory remain **`panasonic_hc`** for migration compatibility.
- Entity IDs, unique IDs and Bluetooth device identity are preserved.

## Install with HACS

1. Add `https://github.com/rndm2/panasonic_hc_bluetooth` to HACS custom repositories,
   category **Integration**.
2. Download **Panasonic H&C Bluetooth** and restart Home Assistant.
3. Accept discovery or add Panasonic H&C Bluetooth and enter a colon-separated MAC address.
   Setup requires a valid status reply; pair the controller first.

### Migrate from david-collett/panasonic_hc

Remove the old repository's
installation in **HACS**, then install this repository before restarting HA. Keep the
existing integration in **Settings → Devices & services**. Do not delete its config entry,
entities, device, statistics or Bluetooth bond. Both repositories use the same domain
and cannot be installed concurrently. Verify the new version and availability after restart.

Rollback: reinstall the previous integration code/version and restart HA.
This release does not migrate stored configuration or rewrite entity identifiers.

## Behavior

Climate supports power, HVAC mode, target temperature (16–32 °C in 0.5 °C steps),
fan speed and eco preset. These temperature limits are inherited and need model-specific
hardware verification. Commands are serialized, followed by a status request, and raise
an HA action error when the controller does not confirm the requested value within 15 seconds.
Status is polled during confirmation because the first reply can still contain the old setting.
The command itself is sent only once. Waiting behind another operation is limited to five
seconds; if the queue is busy the action fails explicitly. Combined temperature/HVAC-mode
actions validate all inputs before sending commands and confirm both returned settings.

Current temperature is a separately timed measurement. Partial or implausible replies retain
the last valid reading; they do not refresh its age. After ten minutes without a valid update,
it becomes unknown. Disconnecting clears it. This avoids flicker without retaining stale data
indefinitely. A failed
multi-command mode change may have partially affected the controller: check its current state.

Climate is polled every 60 seconds while on and every 300 seconds while off. Valid BLE
notifications also update state. Connection failures retry with a 5–300 second backoff.
No heating/cooling action is inferred from temperature alone.

## Reconnect with Bluetooth proxies

Press **Reconnect Bluetooth** on the Panasonic device, or call **Panasonic H&C Bluetooth:
Reconnect Bluetooth** in Developer Tools → Actions and select the integration entry.
The action is also usable when initial setup is retrying and the button is unavailable.

This reloads only the selected Panasonic entry: cancels polling, closes the old BLE connection,
asks HA for a currently connectable route, subscribes to notifications and waits for valid status.
The device lookup is refreshed before each integration connection attempt. HA/its Bluetooth
backend selects the adapter or active ESPHome proxy; this integration does not pin a proxy,
force failover, or restart your ESP32. A stronger unpaired adapter can still be selected.
Concurrent reconnect requests for the same entry are rejected. No pairing data or HVAC settings
are reset. Each proxy still needs its own valid bond to the Panasonic controller.

A controller that stops advertising or a proxy with no free active connection slots cannot be
fixed just by reloading. Check proxy availability and pairing if the action reports failure;
HA will continue setup retries. A successful reconnect means a valid status was received;
it does not prove that every HVAC command or alternate proxy works.

## Energy removal in 0.1.0

Energy tracking is removed: no Daily Energy entity, consumption parser, polling or snapshots.
The old sensor, if registered, may remain unavailable in the entity registry; stored Recorder
history/statistics are not deleted. Climate identity and history are unaffected.

## Troubleshooting and diagnostics

Download diagnostics from the integration page. Diagnostics report connection readiness,
packet-error count and status readiness, without MAC addresses or raw packets.
Enable debug logging for `custom_components.panasonic_hc` when investigating malformed frames.
If setup retries, check pairing, proxy active connections, controller range and whether another
client is occupying the BLE connection. Unknown packet variants are ignored rather than guessed.

## Development

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install '.[test]'
ruff check .
ruff format --check .
mypy
pytest -q --cov=custom_components.panasonic_hc
```

Tests use synthetic packets and mocked BLE connections against real HA classes; they never
send commands to a physical controller. See [CHANGELOG.md](CHANGELOG.md) and
[docs/AUDIT.md](docs/AUDIT.md) for fixes and remaining hardware checks.

## Attribution and licensing

The upstream snapshot contains **no license grant**. Original authorship and Git history
are retained. This repository does not claim ownership of upstream work and does not
apply a new license to it. Attribution is not a substitute for permission; clarify the
upstream license before assuming broad redistribution or relicensing rights.
HACS CI explicitly excludes the license check for this custom repository; this is not
a claim of eligibility for inclusion in the default HACS catalog.

## Pairing

The following instructions are inherited from upstream. The ESPHome example was tested
upstream with 2025.6.1; it has not been revalidated against every later ESPHome release.
The mobile automation example is Android-only. For iOS, use HA Developer Tools to listen
for the pairing event and invoke the confirmation action manually, confirming on the controller too.

### Local Bluetooth Adapter

For setups using a local bluetooth adapter, this can be done from the command line:

```
bluetoothctl
scan on
<Wait for the thermostat to show up and copy the MAC address>
scan off
pair <MAC>
<The thermostat will display a code, confirm it is correct and hit enter on the thermostat.>
trust <MAC>
disconnect <MAC>
exit
```

### Esphome Bluetooth Proxies

If your home assistant uses esphome Bluetooth proxies, some configuration of your esphome device is required. This has been tested with esphome 2025.6.1. Note that 2025.6.0 had a critical bug that breaks pairing. Earlier versions may also work.

1. Ensure bluetooth proxy is enabled and configured for active connections:


```
bluetooth_proxy:
  active: true
```

2. Add a `ble_client` section for your Panasonic Remote. You will need to know the mac address.
The below configuration will send an event to homeassistant when a pairing request is received.
For this to work, your esphome device must be configured to [allow actions](https://esphome.io/components/api.html#api-actions).

```
esp32_ble:
  io_capability: display_yes_no

ble_client:
  - mac_address: "AA:BB:CC:DD:EE:FF"
    id: panasonic_hc
    auto_connect: False
    on_numeric_comparison_request:
      then:
        - homeassistant.event:
            event: esphome.numeric_comparison_request
            data_template:
              pin: !lambda 'return passkey;'
```

3. Add an action (service) to your api section to perform pairing:

```
api:
  ...
  actions:
    - action: numeric_comparison_reply
      then:
        - ble_client.numeric_comparison_reply:
            id: panasonic_hc
            accept: True
```

4. Create automations to simplify paring using the Home Assistant companion mobile app:

This step is optional, as it is possible to manually listen for the pairing event, and manually invoke the pairing action using the Developer Tools in home assistant.
The following currently only works with the Android Companion app, as `TAG` is used to pass the device_id between automations. There may be a better way, but I couldn't find it!

Create an automation to receive the pairing request and send a notification to your phone (replace `<your_phone>` as appropriate):
```
alias: Panasonic HC Pairing Event
description: ""
triggers:
  - trigger: event
    event_type: esphome.numeric_comparison_request
    event_data: {}
conditions: []
actions:
  - action: notify.mobile_app_<your_phone>
    metadata: {}
    data:
      title: Pairing Request
      message: >-
        Panasonic HC wants to pair with {{
        device_attr(trigger.event.data['device_id'], 'name') }}, using PIN: {{
        trigger.event.data['pin'] }}. Please confirm below and on the Panasonic
        Remote
      data:
        tag: "{{trigger.event.data['device_id']}}"
        actions:
          - action: NUMERIC_COMPARISON_CONFIRM
            title: Confirm PIN
mode: single
```

Create a second automation to receive the notification action when Confirm PIN is selected, and invoke the pairing action:

```
alias: Panasonic HC Pairing Action
description: ""
triggers:
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: NUMERIC_COMPARISON_CONFIRM
conditions: []
actions:
  - action: >-
      {{'esphome.'~slugify(device_attr(trigger.event.data['tag'],
      'name'))~'_numeric_comparison_reply' }}
    data: {}
mode: single
```

Now when Home Assistant uses your active bluetooth proxy to connect to the Panasonic remote, you should receive a notification on your phone showing the pairing PIN and requesting confirmation. Compare this PIN with what is displayed on your Panasonic Remote. You must confirm on both the Panasonic remote and your phone (order doesnt matter).
