# Technical references

Primary implementation references:

- [ESP-IDF 5.5.3 documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/)
  and the pinned SDK's NimBLE examples.
- [LVGL 9.5 documentation](https://docs.lvgl.io/9.5/) and
  [SDL desktop port](https://github.com/lvgl/lv_port_pc_vscode).
- [Waveshare board documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.85B)
  and [vendor source](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.85B).
- [Particle Veepeak BLE+ example](https://github.com/particle-iot/ble-gateway-library/tree/main/examples/veepeak):
  useful context for the FFF0/FFF1/FFF2 serial-style profile, not an ESP32
  drop-in driver or compatibility guarantee.

Use pinned SDK/LVGL sources for API details rather than mutable default branches.
Check actual GATT properties and board schematics rather than inferring behavior
from product names.

External examples are references, not automatically approved dependencies.
Review licenses and provenance before copying code, fonts or vehicle profiles.
Original project work uses The Unlicense; third-party code retains its own
licenses and notices, including Apache-licensed vendor components. See the
repository license and third-party notices.
