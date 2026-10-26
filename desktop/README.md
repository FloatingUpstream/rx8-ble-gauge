# LVGL desktop simulator

Linux CMake app using LVGL **9.5.0**, SDL2, and libpng. No ESP-IDF/FreeRTOS
emulation. The UI under `../ui/` is ordinary shared LVGL code; only the platform
initialization and test transport are desktop-specific.

```sh
bash tools/build-desktop.sh
desktop/build/gauge_desktop
```

Run these commands from the repository root. Build helper verifies LVGL commit
`85aa60d18b3d5e5588d7b247abf90198f07c8a63`, uses a local dependency checkout,
builds with the host compiler, and runs CTest. Dependencies are downloaded into
ignored `.local/aux/` by default; an absolute `GAUGE_AUX` selects another cache.

The window is 360×360, with a circular content area. Mouse click switches which
value is prominent (coolant or MAF). This prototype emphasizes coolant and
explicit missing/stale states; it's not the final design.

`...` opens adapter settings. Desktop adapter choices are in-memory fixtures,
not real BLE discovery or a claim of verified adapters:

```sh
desktop/build/gauge_desktop --picker
desktop/build/gauge_desktop --settings
desktop/build/gauge_desktop --picker --empty-scan
```

The same picker/settings source runs on firmware, where discovery, validation
and NVS persistence are real. Host tests exercise selection, menu navigation,
Choose/Forget controls and empty-list rendering.

## Fixtures and headless screenshots

```sh
desktop/build/gauge_desktop --scenario cold
desktop/build/gauge_desktop --scenario normal --maf
desktop/build/gauge_desktop --scenario stale --snapshot desktop/build/stale.png
```

Scenarios: `normal`, `cold`, `hot`, `missing` (MAF unavailable), `stale`,
`disconnected`, `connecting`. These are synthetic readings; the centered `RX-8`
caption deliberately has no simulation label.
Screenshots use LVGL's actual snapshot renderer and SDL's dummy driver, not a
separate approximation. `--seconds N` runs for a bounded interval; combined
with `--snapshot`, captures the final state and exits.

The 40–120 °C arc is an illustrative display range. Colors/arc positions do
not indicate oil warmth or validated warning thresholds. Non-live values are
hidden rather than displayed as trustworthy telemetry.

## Python ELM simulator integration

In one terminal:

```sh
python simulator/elm_sim.py --scenario normal --fragment-bytes 3
```

In another:

```sh
desktop/build/gauge_desktop --elm-port 35000
# Headless end-to-end smoke test:
desktop/build/gauge_desktop --elm-port 35000 --seconds 3 \
  --snapshot desktop/build/elm-live.png
```

The desktop app connects **only to loopback**, initializes the ELM-like session,
polls coolant/MAF, handles fragmented replies, and reconnects after errors.
One outstanding command, bounded buffers/timeouts, and explicit stale/missing
states. It uses the shared headerless Mode 01 decoder in `../protocol/`.
BLE transport and real adapter/ECU behavior are not simulated.

Dependencies: SDL2/libpng development packages, pkg-config, CMake, Ninja and a
C/C++ compiler. See the root README for an example Linux package command.
