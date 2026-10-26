# Contributing

Small, testable changes are welcome. This is a prototype, so reports that
separate host simulation from real hardware/vehicle behaviour are especially
useful.

- Include the board/adapter model, software version and reproduction steps.
- Redact serial numbers, Bluetooth addresses, credentials and private vehicle
  information. Do not attach full flash backups or unreviewed driving captures.
- Use synthetic protocol fixtures where possible.
- Keep OBD operations read-only; arbitrary ECU commands and vehicle control are
  outside the project scope.
- Don't operate debugging tools while driving.

## Checks

```sh
bash tools/bootstrap.sh --no-idf --dev --capture
bash tools/test-desktop.sh
.venv/bin/python -m unittest discover -s simulator -v
.venv/bin/python -m unittest discover -s mechanical -p test_stl_validation.py -v
.venv/bin/pre-commit run --all-files
```

Optional BLE peripheral dependencies: `simulator/requirements-ble.txt`.
Native FreeCAD checks require the installed FreeCAD Python module; see
[mechanical/README.md](mechanical/README.md). A successful compile or render
does not replace a hardware/vehicle validation.

Original contributions are accepted under [The Unlicense](LICENSE). Preserve
third-party licenses and attribution; do not contribute material you cannot
release on those terms.
