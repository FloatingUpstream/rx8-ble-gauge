"""End-to-end tests for the built SDL app and Python ELM server."""

import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("GAUGE_DESKTOP_APP", ROOT / "desktop/build/gauge_desktop"))


@unittest.skipUnless(APP.exists(), "Build desktop simulator first")
class DesktopTests(unittest.TestCase):
    def test_invalid_arguments(self):
        for option, value in (
            ("--seconds", "-1"),
            ("--seconds", "no"),
            ("--seconds", "999999999999999999999"),
            ("--elm-port", "0"),
            ("--elm-port", "65536"),
            ("--elm-port", "35000junk"),
            ("--scenario", "unknown"),
        ):
            with self.subTest(option=option, value=value):
                result = subprocess.run([str(APP), option, value], capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 2)

    def run_app(self, directory, *args):
        output = Path(directory) / "screen.png"
        result = subprocess.run(
            [str(APP), *args, "--snapshot", str(output)],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
            check=True,
        )
        image = output.read_bytes()
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", image[16:24]), (360, 360))
        return result.stdout

    def test_all_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            for scenario in (
                "normal",
                "cold",
                "hot",
                "missing",
                "stale",
                "disconnected",
                "connecting",
                "unsupported-maf",
                "unsupported-coolant",
                "unsupported-both",
            ):
                with self.subTest(scenario=scenario):
                    self.run_app(directory, "--scenario", scenario)
            self.run_app(directory, "--scenario", "normal", "--maf")

    def test_missing_server(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_app(directory, "--elm-port", str(port), "--seconds", "1")
            self.assertIn("link=3", result)
            self.assertIn("coolant_valid=0", result)

    def test_adapter_pages_and_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_app(directory)
            expected_gauge = (Path(directory) / "screen.png").read_bytes()
            result = self.run_app(directory, "--picker", "--click-x", "180", "--click-y", "145")
            self.assertIn("fixture-selected: RX8-ELM-SIM", result)
            self.assertEqual((Path(directory) / "screen.png").read_bytes(), expected_gauge)
            self.run_app(directory, "--settings")
            expected_settings = (Path(directory) / "screen.png").read_bytes()
            self.run_app(directory, "--click-x", "258", "--click-y", "62")
            self.assertEqual((Path(directory) / "screen.png").read_bytes(), expected_settings)
            self.run_app(directory, "--picker", "--empty-scan")
            self.run_app(directory, "--settings", "--empty-scan")

    def test_choose_and_forget_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_app(directory, "--picker")
            expected_picker = (Path(directory) / "screen.png").read_bytes()
            self.run_app(directory, "--settings", "--click-y", "248")
            self.assertEqual((Path(directory) / "screen.png").read_bytes(), expected_picker)
            result = self.run_app(directory, "--settings", "--click-y", "293")
            self.assertIn("fixture-forgotten", result)
            self.assertEqual((Path(directory) / "screen.png").read_bytes(), expected_picker)

    def test_mouse_switch_and_round_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_app(directory, "--maf")
            expected_maf = (Path(directory) / "screen.png").read_bytes()
            self.run_app(directory, "--click")
            self.assertEqual((Path(directory) / "screen.png").read_bytes(), expected_maf)
            self.run_app(directory)
            expected_coolant = (Path(directory) / "screen.png").read_bytes()
            self.run_app(directory, "--click-outside")
            self.assertEqual((Path(directory) / "screen.png").read_bytes(), expected_coolant)

    @contextmanager
    def server(self, scenario="normal", port=None, delay_ms=20, extra=()):
        if port is None:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
        server = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "simulator/elm_sim.py"),
                "--port",
                str(port),
                "--scenario",
                scenario,
                "--fragment-bytes",
                "2",
                "--delay-ms",
                str(delay_ms),
                *extra,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 3
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        self.fail("ELM simulator did not start")
                    time.sleep(0.02)
            yield port
        finally:
            server.terminate()
            server.communicate(timeout=3)

    def with_server(self, scenario, expected, delay_ms=20, seconds=3):
        with self.server(scenario, delay_ms=delay_ms) as port:
            with tempfile.TemporaryDirectory() as directory:
                result = self.run_app(directory, "--elm-port", str(port), "--seconds", str(seconds))
                for text in expected:
                    self.assertIn(text, result)
                return result

    def test_fragmented_live_elm(self):
        self.with_server("normal", ["link=1", "coolant_valid=1", "coolant=87", "maf_valid=1"])

    def test_no_data(self):
        self.with_server(
            "no-data",
            ["link=2", "coolant_valid=0", "maf_valid=0", "coolant_support=0 maf_support=0"],
        )

    def test_unsupported_pids_are_not_polled(self):
        for unsupported, expected in (
            (("10",), "coolant_support=1 maf_support=2"),
            (("05",), "coolant_support=2 maf_support=1"),
            (("05", "10"), "coolant_support=2 maf_support=2"),
        ):
            with self.subTest(unsupported=unsupported), tempfile.TemporaryDirectory() as directory:
                metrics = Path(directory) / "metrics.json"
                extra = ["--metrics", str(metrics)]
                for pid in unsupported:
                    extra += ["--unsupported-pid", pid]
                with self.server(extra=extra) as port:
                    result = self.run_app(directory, "--elm-port", str(port), "--seconds", "3")
                    self.assertIn(expected, result)
                    counts = json.loads(metrics.read_text())["commands"]
                    self.assertGreater(counts["0100"], 0)
                    for pid in unsupported:
                        self.assertNotIn("01" + pid, counts)

    def test_bad_pid_replies_are_not_unsupported(self):
        for fault in ("malformed", "wrong-pid"):
            with self.subTest(fault=fault), self.server(extra=["--fault", fault]) as port:
                with tempfile.TemporaryDirectory() as directory:
                    result = self.run_app(directory, "--elm-port", str(port), "--seconds", "3")
                    self.assertIn("coolant_valid=1", result)
                    self.assertIn("maf_valid=0", result)
                    self.assertIn("coolant_support=1 maf_support=1", result)

    def test_missing_bitmap_still_probes_and_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            metrics = Path(directory) / "metrics.json"
            with self.server(
                extra=[
                    "--fault",
                    "malformed",
                    "--fault-command",
                    "0100",
                    "--metrics",
                    str(metrics),
                ]
            ) as port:
                result = self.run_app(directory, "--elm-port", str(port), "--seconds", "4")
                self.assertIn("coolant_valid=1", result)
                self.assertIn("maf_valid=1", result)
                self.assertIn("coolant_support=1 maf_support=1", result)
                self.assertGreaterEqual(json.loads(metrics.read_text())["commands"]["0100"], 2)

    def test_bad_init_status_is_rejected_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            metrics = Path(directory) / "metrics.json"
            with self.server(
                extra=[
                    "--fault",
                    "bad-status",
                    "--fault-command",
                    "ATE0",
                    "--fault-count",
                    "1",
                    "--metrics",
                    str(metrics),
                ]
            ) as port:
                result = self.run_app(directory, "--elm-port", str(port), "--seconds", "4")
                self.assertIn("coolant_valid=1", result)
                counts = json.loads(metrics.read_text())["commands"]
                self.assertGreaterEqual(counts["ATZ"], 2)

    def test_oversized_response_reconnects_and_recovers(self):
        with self.server(extra=["--fault", "oversized", "--fault-count", "1"]) as port:
            with tempfile.TemporaryDirectory() as directory:
                result = self.run_app(directory, "--elm-port", str(port), "--seconds", "8")
                self.assertIn("link=1", result)
                self.assertIn("coolant_valid=1", result)
                self.assertIn("maf_valid=1", result)

    def test_missing_prompt_times_out_and_clears_old_values(self):
        with self.server(extra=["--fault", "no-prompt"]) as port:
            with tempfile.TemporaryDirectory() as directory:
                result = self.run_app(directory, "--elm-port", str(port), "--seconds", "12")
                self.assertIn("coolant_valid=0", result)
                self.assertIn("maf_valid=0", result)

    def test_command_timeout(self):
        result = self.with_server(
            "normal", ["link=3", "coolant_valid=0", "maf_valid=0"], delay_ms=11000, seconds=11
        )
        self.assertNotIn("link=1", result)

    def test_reconnect_to_changed_server(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "screen.png"
            with self.server() as port:
                app = subprocess.Popen(
                    [
                        str(APP),
                        "--elm-port",
                        str(port),
                        "--seconds",
                        "6",
                        "--snapshot",
                        str(output),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
                )
                time.sleep(1.5)
            try:
                time.sleep(0.4)
                with self.server("hot", port=port):
                    stdout, stderr = app.communicate(timeout=8)
                self.assertEqual(app.returncode, 0, stderr)
                self.assertIn("link=1", stdout)
                self.assertIn("coolant=110", stdout)
            finally:
                if app.poll() is None:
                    app.kill()
                    app.communicate()


if __name__ == "__main__":
    unittest.main()
