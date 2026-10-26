# Shared gauge UI

The same LVGL 9.5.0 UI runs on the 360 × 360 round display and the SDL desktop
application. `ui/gauge_ui.c` renders `gauge_sample_t`; platform code owns input,
transport and LVGL locking. `ui/adapter_ui.c` implements picker/settings pages.

## Current behavior

- Dark circular canvas, centered `RX-8` caption, yellow live accent.
- Coolant primary and MAF secondary; tap/click swaps prominence.
- Thin coolant arc with an illustrative 40–120 °C range.
- Explicit connecting/disconnected/stale/no-data states and `--` placeholders
  instead of stale numbers presented as live.
- Unknown/supported/unsupported PID metadata; one valid field may remain live
  when the other is unavailable.
- `...` opens adapter settings with Choose and Forget.

The arc is **not a validated warning scale**. Coolant does not establish oil
readiness. Fixture values and simulator telemetry are synthetic even though
the gauge has no simulation label; identify the data source outside the gauge.

## Validation

```sh
bash tools/test-desktop.sh
```

The desktop app supports fixtures, TCP telemetry, mouse input and headless PNG
snapshots. Tests cover rendering/state and interaction, not pixel-exact visual
goldens. See [desktop instructions](../desktop/README.md).

Physical display/touch, adapter selection, saved reconnect and Forget have
been exercised on the target board. This is not a sunlight, driver-distance
readability, vibration, heat or mount-retention qualification.

Future work includes telemetry-age transitions, larger-font evaluation and
stable screenshot goldens. Battery/status pages, IMU features and any warnings
require separate implementation and validation; see [roadmap](roadmap.md).
