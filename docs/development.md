# Development

Run commands from the repository root. The supported firmware stack is
**ESP-IDF 5.5.3**, **LVGL 9.5.0**, and the Waveshare
**ESP32-S3-Touch-LCD-1.85B**. Do not substitute another board's BSP.

## Bootstrap and build

Install `git`, `uv`, and the host prerequisites documented by
[ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/get-started/).
The helper downloads a pinned Python 3.12.12, SDK, and ESP32-S3 toolchain:

```sh
bash tools/bootstrap.sh --dev
bash tools/idf.sh -C firmware build
```

Downloads and private captures default to `repo/.local/aux`, ignored by Git.
To use another location, export an **absolute** `GAUGE_AUX` path before running
bootstrap and keep it set for subsequent commands. Optional Python packages go
in `repo/.venv`. `--capture` adds laptop BLE capture dependencies; `--no-idf`
skips SDK/toolchain installation. Bootstrap does not flash hardware, install
system rules, or use sudo.

`tools/idf.sh` runs in a subshell with the pinned environment.
For direct SDK/Python commands, use `source tools/idf-env.sh`.
Avoid mixing SDK versions in the same shell. `GAUGE_ROOT` is supplied by the
wrapper for the vendored QMI8658 component.

```sh
bash tools/idf.sh -C firmware menuconfig
```

The BLE service/characteristic UUIDs are under `Gauge BLE adapter profile`.
Defaults match the tested Veepeak OBDCheck BLE+; changing UUIDs is not a
guarantee of compatibility.

## Flash and inspect

Identify your board's USB port; never copy someone else's device identity.
Ensure your user has access using your operating system's device policy.
Before replacing factory firmware, inspect chip/security settings and consider
a full flash backup. Keep backups private: they may contain credentials, and
encrypted backups may not be independently restorable.

```sh
bash tools/flash.sh /dev/serial/by-id/YOUR_DEVICE
# If already in ROM download mode:
GAUGE_FLASH_BEFORE=no_reset bash tools/flash.sh /dev/serial/by-id/YOUR_DEVICE
```

Alternatively set `GAUGE_PORT`. The helper builds first, then flashes with a
watchdog reset. If USB reset/synchronization fails, follow the board's BOOT/reset
procedure and retry; a failed connection is not evidence of a successful flash.
Do not run a serial reader and flasher on the same port simultaneously.
Opening serial or resetting USB can restart the board and change enumeration.

```sh
source tools/idf-env.sh
python tools/serial_capture.py --port /dev/serial/by-id/YOUR_DEVICE \
  --seconds 20 --output "${GAUGE_AUX}/captures/serial.log"
```

Check logs for initialization,
reconnects and failures, and inspect the physical display. Build/upload success
alone does not validate display, touch, or telemetry.

Optional Linux webcam capture requires ffmpeg and v4l2-ctl:

```sh
bash tools/capture.sh --camera /dev/videoN
```

`GAUGE_CAMERA` is an alternative to `--camera`. Camera controls are unchanged
unless you opt in with `GAUGE_CAMERA_CONTROLS=1`; tuning may need adjustment
for your camera. Output is private and existing files are not overwritten.
Photographs are not calibrated brightness/readability measurements.

## Desktop and tests

Desktop builds require CMake, Ninja, a C/C++ compiler, SDL2 development files
and libpng development files. The build helper fetches the pinned LVGL source.

```sh
bash tools/build-desktop.sh
bash tools/test-desktop.sh
.venv/bin/python -m unittest discover -s simulator -v
.venv/bin/pre-commit run --all-files
```

See [desktop usage](../desktop/README.md), [UI design](ui-design.md), and
[BLE testing](ble-development.md). Optional BLE simulation dependencies are
separate from `--dev`:

```sh
uv pip install --python .venv/bin/python -r simulator/requirements-ble.txt
```

Target-aware static analysis uses Espressif Clang:

```sh
source tools/idf-env.sh
python "$IDF_PATH/tools/idf_tools.py" install esp-clang
# In a fresh shell:
bash tools/tidy.sh
```

Tidy uses a separate compilation database and checks owned sources.
The GCC firmware build remains authoritative; static analysis does not validate
third-party code or physical behavior.

## Validation boundaries

- Host tests: parser/session behavior, UI state, synthetic faults and TCP recovery.
- Physical bench: BLE, display/touch, persistence and reconnect behavior.
- Stationary vehicle: actual adapter profile, ECU support and plausible readings.
- Extended vehicle/power/mechanical tests: still required for deployment.

The first real RX-8/Veepeak success is not broad compatibility certification.
Battery runtime, mounting, sunlight readability and thermal warnings remain
unvalidated. Never configure, debug or operate capture controls while driving.
