# ESP-IDF 5.5.6 bond-reuse investigation

The Panasonic component is not involved in this independent firmware test. A
native ESPHome BLE client reproduces the failure with the HA entry disabled.

## Root cause and regression

IDF 5.5.6 `smp_check_auth_req()` clears BLE keys in RAM after successful
encryption, including encryption using an existing bond. No new key exchange
follows the reuse path. The current session works, but the next connection
cannot reuse its RAM keys and asks to pair again. A later SMP timeout can erase
the still-present NVS bond under the SDK's default central failure policy.

`bond-reuse.patch` gates clearing on `SMP_PAIR_FLAG_ENC_AFTER_PAIR`, the existing
SDK flag for encryption following a new pairing exchange. It preserves legitimate
key replacement after successful pairing and retains keys on failed encryption.

Run `python3 tools/proxy_security/test_sdk_bond_reuse.py`. It compiles the extracted
actual C handler with stubbed surrounding stack calls. The original must fail
bond reuse, while the corrected handler must pass reuse, successful new pairing
and failed encryption cases. This is not a full Bluetooth-stack simulation.
The extracted SDK fixture retains its Apache-2.0 attribution in the source and
`SDK-NOTICE.txt`.

## Isolated firmware build

`prepare_sdk_patch.py` creates an isolated IDF tree and replaces only the SMP
source file. It verifies that the shared SDK source remains unchanged. Its default
paths target the ESPHome add-on's IDF 5.5.6 installation and `/data` build storage.
Run it inside that add-on alongside `sdk_bond_fix.py`, after reviewing the paths.
It does not upload firmware, restart a device, access credentials or remove bonds.

Use the corrected `bt` component through the target device's YAML so a normal
future ESPHome build retains the fix:

```yaml
esp32:
  framework:
    type: esp-idf
    version: 5.5.6
    components:
      - name: bt
        path: /data/panasonic-idf-5.5.6-bond-reuse/components/bt
    sdkconfig_options:
      CONFIG_BT_BLE_SMP_REMOVE_BOND_ON_PAIR_FAIL_AS_CENTRAL: "n"
```

The final option prevents a failed pairing from implicitly deleting NVS bonds.
Explicit bond removal remains available. Encryption, numeric comparison and
hardened repairing stay enabled. This is a local workaround for the pinned SDK,
not a claim that every SDK or ESPHome version has the same defect. Reassess it
before upgrading the framework. Do not silently reuse this component with a
different IDF version.

## Independent protected-GATT check

`panasonic_security_probe.h` is a diagnostic `BLEClientNode`. Include it in the
ESPHome config, construct `PanasonicSecurityProbe(id(your_ble_client))` once after
setup, and invoke `start()` from an explicit API action. It discovers the
notification UUID and CCCD, enables it with a write response, logs the controller's
actual completion status, then restores the CCCD. No pairing, bond removal,
auto-connect or HVAC commands are performed. The pending operation is bounded
to ten seconds. After a timeout it refuses another test until reconnect, so a late completion cannot be mistaken for a newer operation.

A local submission result of zero does not establish success. The evidence is
`Protected CCCD write completed: enable=1 status=0`, followed by successful
cleanup (`enable=0 status=0`). Check this after both reconnect and reboot, together
with authentication and bond-presence evidence.

A second raw ESPHome API client cannot simply run this test alongside HA:
Bluetooth replies go to the active advertisements subscriber. Earlier probes
without subscriber ownership produced invalid timeout evidence. Do not steal
HA's Bluetooth subscription just to make a diagnostic client receive replies.
