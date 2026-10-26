# Read-only vehicle capture

The laptop logger initializes an ELM BLE bridge, discovers Mode 01 support and
requests coolant `0105`, MAF `0110`, RPM `010C` and speed `010D`.
It is diagnostic polling, **not a passive CAN broadcast dump**. It offers no
DTC clearing, VIN requests, ECU configuration or arbitrary command input.
The firmware gauge itself displays only coolant and MAF.

First real RX-8/Veepeak OBDCheck BLE+ testing established the FFF0 service,
FFF1 notifications, FFF2 acknowledged writes, and valid coolant/MAF replies.
The ESP gauge also had its first reported in-car success. Later laptop
RPM/speed polling and the revised sampling schedule still need real-car
validation. No broad vehicle/adapter compatibility is claimed.

## Prepare while stationary

```sh
bash tools/bootstrap.sh --capture
.venv/bin/python tools/capture_ble.py --scan
```

Choose the actual adapter address from your own scan. Scanning only lists
candidates. Turn off the gauge and close phone OBD apps before connecting:
assume one central at a time. USB removal may leave a battery-powered gauge on.

```sh
.venv/bin/python tools/capture_ble.py \
  --address AA:BB:CC:DD:EE:FF --seconds 120
```

The address above is a placeholder. Default UUIDs are FFF0/FFF1/FFF2, with
single-characteristic write fallback and acknowledged-write preference.
Inspect service discovery and completed responses before any longer capture.
Start with ignition on, then engine idling **outdoors**, never in an enclosed
space. `NO DATA`/`CAN ERROR` can reflect ECU/bus state while BLE remains connected.

Do not drive to debug a failed stationary test. Start, stop and inspect logging
only while parked. Secure equipment away from pedals, controls and airbags;
provide ventilation and power. Do not interact with the gauge/laptop while driving.
Capture permission and safe installation are the operator's responsibility.

## Optional background monitor

On Linux with a user systemd manager:

```sh
bash tools/monitor.sh start --address AA:BB:CC:DD:EE:FF
bash tools/monitor.sh status
bash tools/monitor.sh logs
bash tools/monitor.sh stop
```

The helper saves the selected address privately for later `start` calls.
It manages a temporary capture service and sleep/idle/lid inhibitor, not a
permanent system unit or desktop power policy. Confirm the service and inhibitor
succeed while parked. Ctrl-C in `logs` stops the viewer, not the capture.
`stop` manages this helper's service, not manually launched captures.

Options after `start` pass to the logger, for example `--seconds 3600`.
`GAUGE_PYTHON` can select an absolute Python executable; the default is the
repository's `.venv/bin/python`.

## Private output and timing

Default output is a new directory under `repo/.local/aux/captures`; set
`GAUGE_AUX` to an absolute alternate cache location, or `--out PATH` to a new
capture directory. Existing captures are not overwritten. Keep output private:
addresses, timestamps and vehicle telemetry can identify devices and activity.

- `rx.bin`: unchanged notification bytes in receipt order.
- `tx.bin`: attempted commands including CR; attempts do not prove ECU receipt.
- `events.jsonl`: command/connection IDs, UTC and monotonic receipt timestamps,
  raw offsets, chunk boundaries, completed responses, capabilities and errors.

No decoded CSV is generated. Receipt times are not ECU sampling times, and
sequential PID readings are not simultaneous.

One request is outstanding at a time. Default timeout is ten seconds, reconnect
delay two seconds and prompt assembly limit 4096 bytes. Confirmed unsupported
PIDs are skipped; unknown support still probes, and an empty requested-PID map
is rechecked every thirty seconds.

MAF receives spare bandwidth, with at most one auxiliary request between MAF
requests. Default minimum auxiliary periods after replies are coolant ten
seconds, RPM five seconds and speed five seconds. Configure via
`--coolant-period`, `--rpm-period` and `--speed-period`. These are minimum
periods, not guaranteed sampling rates; ELM/ECU latency limits resolution.

Default capture limits are two hours or 256 MiB. Output uses restrictive
permissions and is fsynced on normal shutdown, but abrupt power loss can leave
an incomplete tail. Retain all three files when investigating failures.

Synthetic tests and one successful vehicle test do not validate battery runtime,
mount retention, all driving conditions, warning thresholds or oil readiness.
See [roadmap](roadmap.md) for remaining work.
