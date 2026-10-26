"""Bash launcher ownership/lifecycle tests using mock commands, not system changes."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools/monitor.sh"


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        commands = {
            "systemctl": """#!/bin/bash
case "$*" in
 *is-active*) test -f "$TEST_STATE/active";;
 *stop*) rm -f "$TEST_STATE/active"; echo stop >>"$TEST_STATE/actions";;
 *show*) test "${TEST_STOP_ERROR:-0}" = 0 || exit 1; echo "${TEST_LOAD_STATE:-loaded}";;
 *) exit 2;;
esac
""",
            "systemd-run": """#!/bin/bash
printf '%s\\n' "$@" >"$TEST_STATE/runner-args"
test "${TEST_FAIL:-0}" = 0 || exit 1
while [[ $# -gt 0 ]]; do
 if [[ "$1" == --out && "${TEST_NO_EVENTS:-0}" == 0 ]]; then
  mkdir -p "$2"; echo '{}' >"$2/events.jsonl"
 fi
 shift
done
touch "$TEST_STATE/active"
""",
            "sleep": "#!/bin/bash\nexit 0\n",
        }
        for name, contents in commands.items():
            file = bin_dir / name
            file.write_text(contents)
            file.chmod(0o700)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GAUGE_AUX": str(self.path / "aux"),
            "TEST_STATE": str(self.path),
            "VEEPEAK_ADDRESS": "",
            "GAUGE_PYTHON": sys.executable,
            "TEST_FAIL": "0",
            "TEST_NO_EVENTS": "0",
            "TEST_STOP_ERROR": "0",
            "TEST_LOAD_STATE": "loaded",
        }

    def run_script(self, *args, code=0):
        result = subprocess.run(
            ["bash", str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_start_stop_and_remember_address(self):
        self.run_script("start", "--address", "AA:BB:CC:DD:EE:FF", "--seconds", "30")
        arguments = (self.path / "runner-args").read_text()
        self.assertIn("--what=sleep:idle:handle-lid-switch", arguments)
        self.assertIn("--property=KillMode=control-group", arguments)
        self.assertIn("--property=TimeoutStopSec=30s", arguments)
        self.assertIn("systemd-inhibit\n--no-ask-password", arguments)
        self.assertIn("--seconds\n30", arguments)
        self.assertIn(f"{sys.executable}\n", arguments)
        self.assertEqual(
            (self.path / "aux/monitor/address").read_text().strip(), "AA:BB:CC:DD:EE:FF"
        )
        self.run_script("start", code=1)  # no concurrent second monitor
        foreign = self.path / "unrelated-inhibitor"
        foreign.touch()
        self.run_script("stop")
        self.assertFalse((self.path / "active").exists())
        self.assertTrue(foreign.exists())
        self.run_script("stop")
        self.run_script("start")  # reuses the private address

    def test_bad_inputs_and_launch_failure(self):
        self.run_script("start", code=2)
        self.run_script("start", "--address", "not-a-mac", code=2)
        self.run_script("start", "--address", "AA:BB:CC:DD:EE:FF", "--scan", code=2)
        self.env["TEST_FAIL"] = "1"
        self.run_script("start", "--address", "AA:BB:CC:DD:EE:FF", code=1)
        self.assertFalse((self.path / "aux/monitor/address").exists())

    def test_launcher_output_cannot_be_overridden(self):
        for option in ("--out", "--out=/tmp/foreign", "--address=AA:BB:CC:DD:EE:FF"):
            self.run_script("start", "--address", "AA:BB:CC:DD:EE:FF", option, code=2)
        self.assertFalse((self.path / "runner-args").exists())

    def test_startup_timeout_stops_owned_service(self):
        self.env["TEST_NO_EVENTS"] = "1"
        self.run_script("start", "--address", "AA:BB:CC:DD:EE:FF", code=1)
        self.assertFalse((self.path / "active").exists())
        self.assertEqual((self.path / "actions").read_text(), "stop\n")
        self.assertFalse((self.path / "aux/monitor/address").exists())

    def test_stop_manager_error_propagates_and_missing_unit_is_harmless(self):
        self.env["TEST_STOP_ERROR"] = "1"
        self.run_script("stop", code=1)
        self.env["TEST_STOP_ERROR"] = "0"
        self.env["TEST_LOAD_STATE"] = "not-found"
        self.run_script("stop")
        self.assertFalse((self.path / "actions").exists())

    def test_interpreter_must_exist_and_be_absolute(self):
        for interpreter in (str(self.path / "missing-python"), "python3"):
            self.env["GAUGE_PYTHON"] = interpreter
            self.run_script("start", "--address", "AA:BB:CC:DD:EE:FF", code=1)
        self.assertFalse((self.path / "runner-args").exists())


if __name__ == "__main__":
    unittest.main()
