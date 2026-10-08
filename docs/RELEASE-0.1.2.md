# Panasonic H&C Bluetooth 0.1.2

Fixes current-temperature flicker when changing the target: partial replies preserve the last
valid measurement without refreshing its age. Measurements expire after ten minutes and are
cleared on disconnect. Repeated invalid readings no longer bypass the jump filter.

Also fixes combined temperature/mode actions, adds a bounded command queue, rejects reconnect
for disabled entries and supervises unexpected polling errors. Domain, entity IDs and pairing
are unchanged; no energy accounting is restored.

See [production review](https://github.com/rndm2/panasonic_hc_bluetooth/blob/main/docs/REVIEW-0.1.2.md)
and [validation](https://github.com/rndm2/panasonic_hc_bluetooth/blob/main/docs/VALIDATION.md).
Update through HACS and restart Home Assistant.
