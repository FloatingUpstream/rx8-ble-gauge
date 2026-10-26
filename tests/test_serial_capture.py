"""Optional pyserial tool tests; raw handover uses only a disposable Linux PTY."""

import importlib.util
import os
import pty
import tempfile
import threading
import time
import tty
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

HAS_SERIAL = importlib.util.find_spec("serial") is not None
if HAS_SERIAL:
    spec = importlib.util.spec_from_file_location(
        "serial_capture", Path(__file__).resolve().parent.parent / "tools/serial_capture.py"
    )
    CAPTURE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(CAPTURE)


@unittest.skipUnless(HAS_SERIAL, "Run with IDF Python for pyserial")
class SerialCaptureTests(unittest.TestCase):
    def test_handover_preserves_raw_bytes(self):
        master, slave = pty.openpty()
        try:
            tty.setraw(slave)
            port = os.ttyname(slave)
            argv = f"python\0tools/serial_capture.py\0--port\0{port}\0".encode()
            command = Mock()
            command.read_bytes.side_effect = [argv, argv, b""]
            payload = b"ELM link=1\r\n"

            def send():
                time.sleep(0.05)
                os.write(master, payload)

            sender = threading.Thread(target=send)
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "log"
                args = SimpleNamespace(handover_pid=123, port=port, output=output, seconds=0.2)
                sender.start()
                with patch.object(CAPTURE, "Path", return_value=command):
                    CAPTURE.handover(args)
                sender.join()
                self.assertEqual(output.read_bytes(), payload)
        finally:
            os.close(master)
            os.close(slave)

    def test_wrong_process_or_port_rejected_before_open(self):
        for argv in (
            b"python\0something_else.py\0--port\0/dev/ttyFAKE\0",
            b"python\0tools/serial_capture.py\0--port\0/dev/ttyOTHER\0",
        ):
            with self.subTest(argv=argv):
                command = Mock()
                command.read_bytes.return_value = argv
                args = SimpleNamespace(handover_pid=123, port="/dev/ttyFAKE")
                with (
                    patch.object(CAPTURE, "Path", return_value=command),
                    patch.object(CAPTURE.os, "open") as opened,
                ):
                    with self.assertRaises(RuntimeError):
                        CAPTURE.handover(args)
                    opened.assert_not_called()

    def test_handover_wait_is_bounded(self):
        command = Mock()
        command.read_bytes.return_value = b"python\0tools/serial_capture.py\0--port\0/dev/ttyFAKE\0"
        args = SimpleNamespace(handover_pid=123, port="/dev/ttyFAKE")
        with (
            patch.object(CAPTURE, "Path", return_value=command),
            patch.object(CAPTURE.os, "open", return_value=321),
            patch.object(CAPTURE.os, "close") as closed,
            patch.object(CAPTURE.time, "monotonic", side_effect=[0, 601]),
        ):
            with self.assertRaises(TimeoutError):
                CAPTURE.handover(args)
            closed.assert_called_once_with(321)


if __name__ == "__main__":
    unittest.main()
