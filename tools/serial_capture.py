"""Bounded passive serial log capture; run with the IDF Python environment."""

import argparse
import math
import os
import select
import time
from pathlib import Path

import serial


def handover(args):
    """Keep the already-open tty alive; don't touch termios or modem lines."""
    command = Path(f"/proc/{args.handover_pid}/cmdline")
    argv = command.read_bytes().split(b"\0")
    if not any(item.endswith(b"/serial_capture.py") for item in argv):
        raise RuntimeError("Handover predecessor is not serial_capture.py")
    port_index = argv.index(b"--port") + 1
    if os.fsdecode(argv[port_index]) != args.port:
        raise RuntimeError("Handover predecessor uses another port")
    descriptor = os.open(args.port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        deadline = time.monotonic() + 600
        while True:
            try:
                active = command.read_bytes()
            except FileNotFoundError:
                break
            if not active:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Predecessor did not finish within ten minutes")
            time.sleep(0.1)
        deadline = time.monotonic() + args.seconds
        with args.output.open("wb") as output:
            while time.monotonic() < deadline:
                if select.select([descriptor], [], [], 0.2)[0]:
                    data = os.read(descriptor, 4096)
                    if not data:
                        raise RuntimeError("Serial device disappeared")
                    output.write(data)
                    output.flush()
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--handover-pid",
        type=int,
        help="Linux: continue after an existing same-port capture without "
        "changing control lines; predecessor must finish within ten minutes",
    )
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.handover_pid is not None and args.handover_pid <= 1:
        parser.error("--handover-pid must identify an existing capture process")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.handover_pid is not None:
        handover(args)
        print(args.output)
        return
    # Avoid toggling reset control lines intentionally. USB drivers may still
    # react to opening the port; this is not a reset or bootloader-entry tool.
    port = serial.Serial(port=None, baudrate=115200, timeout=0.2, exclusive=True)
    port.dtr = False
    port.rts = False
    port.port = args.port
    port.open()
    try:
        deadline = time.monotonic() + args.seconds
        with args.output.open("wb") as output:
            while time.monotonic() < deadline:
                data = port.read(port.in_waiting or 1)
                if data:
                    output.write(data)
                    output.flush()
    finally:
        port.close()
    print(args.output)


if __name__ == "__main__":
    main()
