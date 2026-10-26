# Local OBD/ELM simulator

Standard-library Python TCP server; no external dependencies.

```sh
python simulator/elm_sim.py
python simulator/elm_sim.py --scenario hot --fragment-bytes 3
python -m unittest discover -s simulator -v
```

Connect to `127.0.0.1:35000`, send ASCII ELM commands terminated with CR, and
read until the `>` prompt. Separate ELM settings per connection. Supports basic
initialization, PID support bitmaps, coolant, RPM, speed, intake temperature,
MAF and ECU voltage. Cold/normal/hot scenarios change coolant; RPM/speed/MAF
cycle over time. `no-data` and delayed/fragmented responses exercise failures.

Values are **synthetic test inputs**, not validated RX-8 traces, warning
thresholds, or a physically coherent engine model. No DTC clearing/ECU writes.
Unsupported commands return `?`; unsupported PIDs return `NO DATA`.

## Capabilities and deterministic faults

Both TCP and BLE frontends accept:

```sh
# Advertise a valid support bitmap excluding MAF:
python simulator/elm_sim.py --unsupported-pid 10

# Three oversized MAF replies, then normal; budget survives reconnects:
python simulator/elm_sim.py --fault oversized --fault-command 0110 \
  --fault-every 5 --fault-count 3 --metrics /tmp/elm-metrics.json
```

Data PID arguments are hexadecimal. A valid bitmap excluding a PID is different
from `--scenario no-data`, which makes the support bitmap unavailable too.
Fault modes: malformed, wrong-pid, oversized, no-prompt, silent, bad-status.
`--fault-after N` skips the first N matching commands; `--fault-every N` faults
every Nth match thereafter; count 0 means unlimited. Metrics are atomically
updated JSON counts with bounded command keys. Signals remain synthetic.

BLE additionally supports
`--profile split|single|no-response|wrong-service|no-notify|no-write`.
`no-response` accepts only write-without-response on TX.
`single` uses FFF1 for writes and notifications. The incompatible profiles are
test fixtures, not alternative adapter profiles. Fake-server unit tests verify
their construction; physical firmware rejection still needs validation.

## BLE peripheral frontend

The TCP backend is dependency-free. The optional BLE frontend advertises the
same synthetic session engine through a Linux Bluetooth adapter:

```sh
bash tools/bootstrap.sh --no-idf --dev --capture
uv pip install --python .venv/bin/python -c tools/constraints-tools.txt \
  -r simulator/requirements-ble.txt
.venv/bin/python simulator/ble_sim.py --scenario normal
```

It advertises **RX8-ELM-SIM**, not a real Veepeak adapter. BLE advertising
requires a suitable controller and BlueZ setup; host unit tests do not prove
physical-radio behaviour. See [BLE development](../docs/ble-development.md).

The desktop TCP transport already shares the production ELM session/decoder.
For UI-only work, native fixtures bypass transport entirely. Neither frontend
communicates with an ECU or produces evidence of real sensor behaviour.

Leave the TCP server bound to loopback unless deliberately testing another
network interface: it has no authentication. Sanitized trace replay and broader
ignition sequences are possible future work, not current capabilities.
