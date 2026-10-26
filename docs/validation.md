# Validation snapshot

This describes local checks of the public source tree, not a safety
certification or a new real-car test.

## Clean setup and builds

- Started from source files only, with a new project-local dependency cache.
- Downloaded the pinned standalone Python 3.12.12, ESP-IDF 5.5.3 checkout,
  submodules and ESP32-S3 toolchains through `tools/bootstrap.sh`.
- Built the firmware from a new build directory successfully.
- Downloaded the pinned LVGL 9.5.0 source and built the desktop application from
  a new build directory successfully.
- No existing private workspace, capture files or adapter state was required.
- No board was flashed, ECU connected or host device permissions changed.

## Checks

| Check | Local result |
| --- | --- |
| Native protocol/render CTests | 6 passed |
| Application, UI, capture, monitor and serial Python tests | 41 passed |
| Simulator tests, including optional BLE construction fixtures | 15 passed |
| CAD, STL, export and PNG-privacy tests | 17 passed |
| Blender scene/packed resource/geometry binding check | Passed |
| Small render regeneration + metadata stripping smoke test | Passed |

Fresh UI artwork was generated with the shared LVGL snapshot renderer.
All depicted readings and device choices are explicitly synthetic.
The studio scene retains the exact verified cradle mesh; device details are
approximate presentation geometry.

The GitHub Actions workflow builds firmware and exercises desktop/Python
checks. A configured workflow is not evidence of a successful hosted run;
check the repository's Actions results after publishing.

## Reproduce

See [development](development.md), [contributing](../CONTRIBUTING.md),
[BLE development](ble-development.md), and the
[mechanical workflows](../mechanical/README.md).
Hardware/vehicle observations and remaining limitations are described in the
[hardware guide](hardware.md) and [roadmap](roadmap.md).

Digital validity does not establish printed fit, material/adhesive suitability,
retention over bumps, battery runtime or validated temperature warnings.
