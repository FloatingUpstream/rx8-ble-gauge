"""Test our application-level soak acceptance criteria, without a radio."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("soak_report", ROOT / "tools/analyze-ble-soak.py")
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def sample(ms, link=1, coolant=1, maf=1):
    return (
        f"I ({ms}) gauge_ble: ELM link={link} coolant=87 valid={coolant} "
        f"MAF_centi=1240 valid={maf} support=1/1\n"
    )


class SoakReportTests(unittest.TestCase):
    def analyze(self, text, expected):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "serial.log"
            output = Path(directory) / "report.json"
            log.write_text(text)
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "analyze-ble-soak.py",
                        str(log),
                        "--steady-from-ms",
                        "2000",
                        "--min-seconds",
                        "10",
                        "--output",
                        str(output),
                    ],
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(REPORT.main(), 0 if expected else 1)
            self.assertEqual(json.loads(output.read_text())["passed"], expected)

    def test_healthy_phase_excludes_deliberate_earlier_faults(self):
        self.analyze(
            sample(1000, link=3, coolant=0, maf=0)
            + "I (1500) gauge_ble: Disconnected: reason=534\n"
            + sample(2000)
            + sample(7000)
            + sample(12000),
            True,
        )

    def test_unexpected_disconnect_or_invalid_sample(self):
        healthy = sample(2000) + sample(7000) + sample(12000)
        self.analyze(healthy + "I (13000) gauge_ble: Disconnected: reason=531\n", False)
        self.analyze(sample(2000) + sample(7000, maf=0) + sample(12000), False)

    def test_short_or_gapped_capture(self):
        self.analyze(sample(2000) + sample(7000), False)
        self.analyze(sample(2000) + sample(14000), False)

    def test_reset_or_panic_invalidates(self):
        healthy = sample(2000) + sample(7000) + sample(12000)
        self.analyze(healthy + sample(3000), False)
        self.analyze("ESP-ROM:\nESP-ROM:\n" + healthy, False)
        self.analyze(healthy + "abort() was called\n", False)


if __name__ == "__main__":
    unittest.main()
