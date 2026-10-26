# BLE development and testing

The firmware is a NimBLE central with one adapter connection. Its shared ELM
session and decoder also run in the desktop TCP application.
Bench tests cover selection, saved reconnect, Forget, server loss, no-data and
fault recovery. A first real RX-8/Veepeak test also succeeded; neither synthetic
tests nor that first success establish broad compatibility or long-term reliability.

## Adapter profile and selection

Default GATT profile:

| Purpose | UUID |
| --- | --- |
| Service | `FFF0` |
| Receive notifications | `FFF1` |
| Command writes | `FFF2` |

A writable receive characteristic is accepted if the separate TX characteristic
is absent. The client checks properties and subscribes through the CCCD;
acknowledged writes are preferred when available.

Named scan results are candidates, not verified OBD adapters. Selection connects
only to that address. After profile checks and ELM initialization including
`ATI`, public/static-random identities can be saved in NVS (`gauge_ble`,
`peer_v1`). Rotating private addresses are session-only; identity resolution
is not implemented. Saved reconnect never silently switches to another adapter.
The gauge's `...` control opens Choose/Forget settings.

BLE callbacks enqueue events; a worker owns the ELM session and takes the BSP
display lock for UI updates. Minimal GAP/GATT server services remain enabled
to handle reciprocal ATT requests, even though the application never advertises.
Disabling this previously caused repeatable bench disconnects.

## Session behavior

- CR-terminated commands, one outstanding request, prompt-delimited replies.
- Initialization: `ATZ`, `ATE0`, `ATL0`, `ATS0`, `ATH0`, `ATSP0`, `ATI`.
- `0100` discovers standard Mode 01 support for coolant `05` and MAF `10`.
- Valid support maps distinguish unsupported fields from unknown support.
  Unknown support still permits direct probes; `NO DATA` is not proof of absence.
- Fragmented responses use a bounded 512-byte buffer. Binary/NUL input and
  overflow are rejected rather than partially decoded.
- Whole-command timeout is ten seconds; successful samples expire after three
  seconds. Disconnects invalidate readings. Late replies do not restore stale data.
- Discovery retries between PID cycles; when both fields are known unsupported,
  support is rechecked at thirty-second intervals.

The gauge requests coolant/MAF only. It does not clear DTCs, configure ECUs or
provide validated thermal/oil-readiness warnings.

## Run a synthetic BLE adapter

Follow [development setup](development.md), then:

```sh
uv pip install --python .venv/bin/python -r simulator/requirements-ble.txt
.venv/bin/python simulator/ble_sim.py --scenario normal --fragment-bytes 3
```

Linux requires running BlueZ, a powered peripheral-capable controller, and
permission to register GATT/advertising. The simulator installs no system rules.
Its advertised name is `RX8-ELM-SIM`, not Veepeak. Normal/cold/hot/no-data
scenarios are synthetic fixtures, not a vehicle thermal model.
See [simulator instructions](../simulator/README.md) for fault options.

## Repeatable checks

```sh
bash tools/test-desktop.sh
.venv/bin/python -m unittest discover -s simulator -v
bash tools/tidy.sh
```

Host tests cover support discovery, fragmentation, strict initialization,
timeouts, stale data, malformed/oversized replies and reconnection. Mocked BLE
tests do not exercise a radio. Virtual-time stress tests are not real-time soaks.

Optional host sanitizers and real-time TCP soak:

```sh
CC=clang CXX=clang++ GAUGE_DESKTOP_BUILD="$PWD/desktop/build/asan" \
  bash tools/build-desktop.sh -DGAUGE_SANITIZERS=ON
ASAN_OPTIONS=detect_leaks=0 GAUGE_DESKTOP_APP="$PWD/desktop/build/asan/gauge_desktop" \
  python3 -m unittest discover -s tests -v
.venv/bin/python tools/soak.py --seconds 600 --profile oversized \
  --output-dir .local/aux/captures/host-soak
```

Sanitizers cover project-owned host code, not external LVGL. RSS drift alone
does not prove absence of leaks.

For a physical bench test, verify saved reconnect, no-data placeholders,
unsupported-PID suppression, adapter loss/recovery and fresh readings afterward.
Keep logs private and assess resets, unexpected disconnects and sample gaps,
not just final screenshots. `tools/analyze-ble-soak.py --help` describes log
acceptance checks. Prior bench testing supports the current radio configuration,
but does not validate multi-hour vehicle use, all GATT failures or new adapters.

For actual vehicle checks, follow [stationary capture instructions](real-car-capture.md).
