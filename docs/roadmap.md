# Roadmap and validation status

## Working prototype

- ESP-IDF 5.5.3 / LVGL 9.5.0 on Waveshare ESP32-S3-Touch-LCD-1.85B.
- Shared round UI and ELM decoder/session across firmware and desktop.
- Read-only standard Mode 01 coolant/MAF polling over Veepeak-style BLE.
- Adapter picker, verified stable-identity persistence, reconnect and Forget.
- Unsupported/unknown/no-data handling, stale-value expiry and fault tests.
- First real RX-8/Veepeak OBDCheck BLE+ coolant/MAF success, plus bench testing.

This is not a broadly compatible OBD product or a validated warning instrument.

## Next: repeatable vehicle validation

1. Repeat stationary starts, ignition transitions, adapter loss and recovery.
2. Validate the laptop logger's RPM/speed requests and revised sampling schedule.
3. Measure response latency, sample gaps, supported PIDs and multi-ECU behavior
   across additional vehicles/adapters before claiming compatibility.
4. Extend radio soaks and candidate-rejection tests, including failed profile
   verification and persistence behavior.

## Power, enclosure and usability

- Measure battery capacity/runtime, charging behavior and state-of-charge accuracy.
- Define safe on/off/sleep behavior; investigate IMU wake only after checking wiring.
- Prototype and test the [mechanical design](mechanical-design.md) for retention,
  vibration, cabin heat and safe placement.
- Test sunlight and driver-distance readability before changing font/layout.

Battery runtime and mount safety are currently unverified.

## Later, only with evidence

- Consider private-address identity resolution and additional BLE profiles.
- Add battery/status or calibrated IMU pages with separate tests.
- Investigate warnings only after establishing vehicle-specific sensor meaning,
  thresholds, hysteresis and failure behavior. No validated thermal warnings or
  oil-readiness inference exist today.

Keep configuration/testing stationary. Do not rely on this prototype instead of
factory instruments or safety warnings.
