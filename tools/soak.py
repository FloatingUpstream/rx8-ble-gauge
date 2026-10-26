#!/usr/bin/env python3
"""Real-time desktop/TCP soak with final telemetry, command counts and Linux RSS."""

import argparse
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rss(pid):
    try:
        status = Path(f"/proc/{pid}/status").read_text()
        return int(re.search(r"^VmRSS:\s+(\d+)", status, re.MULTILINE)[1])
    except (OSError, TypeError):
        return None


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--app", type=Path, default=ROOT / "desktop/build/gauge_desktop")
    parser.add_argument(
        "--profile", choices=["normal", "malformed", "oversized", "no-prompt"], default="normal"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.seconds < 20 or not args.app.is_file():
        parser.error("seconds must be >=20 and app must exist")
    directory = args.output_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    metrics = directory / "metrics.json"
    command = [
        sys.executable,
        str(ROOT / "simulator/elm_sim.py"),
        "--port",
        str(port),
        "--fragment-bytes",
        "2",
        "--metrics",
        str(metrics),
    ]
    if args.profile != "normal":
        command += ["--fault", args.profile, "--fault-every", "17", "--fault-count", "4"]
    samples = []
    server = app = None
    try:
        with (
            (directory / "server.log").open("w") as server_log,
            (directory / "app.log").open("w") as app_log,
        ):
            server = subprocess.Popen(command, stdout=server_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if time.monotonic() > deadline or server.poll() is not None:
                        raise RuntimeError("Server didn't start; inspect server.log") from None
                    time.sleep(0.05)
            app = subprocess.Popen(
                [
                    str(args.app.resolve()),
                    "--elm-port",
                    str(port),
                    "--seconds",
                    str(args.seconds),
                    "--snapshot",
                    str(directory / "final.png"),
                ],
                stdout=app_log,
                stderr=subprocess.STDOUT,
                env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
            )
            started = time.monotonic()
            while app.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > args.seconds + 20:
                    raise RuntimeError("App exceeded deadline")
                samples.append(
                    {
                        "seconds": round(elapsed, 2),
                        "app_rss_kib": rss(app.pid),
                        "server_rss_kib": rss(server.pid),
                    }
                )
                time.sleep(1)
            exit_code = app.returncode
        output = (directory / "app.log").read_text()
        success = (
            exit_code == 0
            and all(
                token in output
                for token in (
                    "link=1",
                    "coolant_valid=1",
                    "maf_valid=1",
                    "coolant_support=1 maf_support=1",
                )
            )
            and not re.search(r"AddressSanitizer|LeakSanitizer|runtime error:", output)
        )
        steady = [
            s["app_rss_kib"] for s in samples if s["seconds"] >= 20 and s["app_rss_kib"] is not None
        ]
        drift = statistics.median(steady[-10:]) - statistics.median(steady[:10]) if steady else None
        summary = {
            "profile": args.profile,
            "duration_seconds": args.seconds,
            "app_exit": exit_code,
            "final_telemetry_ok": success,
            "steady_app_rss_drift_kib": drift,
            "metrics": json.loads(metrics.read_text()),
            "samples": samples,
            "note": "RSS drift is an observation, not proof of leak absence. Virtual protocol "
            "soak and physical BLE soak are separate tests.",
        }
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(
            f"{args.profile}: final telemetry {'PASS' if success else 'FAIL'}, "
            f"steady RSS drift={drift} KiB; {directory / 'summary.json'}"
        )
        return 0 if success else 1
    finally:
        stop(app)
        stop(server)


if __name__ == "__main__":
    sys.exit(main())
