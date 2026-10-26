"""Capture-client tests without a radio or ECU; unchanged bytes are the evidence."""

import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HAS_BLEAK = importlib.util.find_spec("bleak") is not None
if HAS_BLEAK:
    spec = importlib.util.spec_from_file_location(
        "capture_ble", Path(__file__).resolve().parent.parent / "tools/capture_ble.py"
    )
    CAPTURE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(CAPTURE)


def args():
    return SimpleNamespace(
        address="TEST",
        timeout=0.1,
        gap=0.001,
        retry=0.001,
        service=CAPTURE.ble_uuid("fff0"),
        rx=CAPTURE.ble_uuid("fff1"),
        tx=CAPTURE.ble_uuid("fff2"),
    )


class FakeClient:
    def __init__(self, disconnected_callback=None, disconnect_pid=False, no_response=False):
        self.callback = disconnected_callback
        self.disconnect_pid = disconnect_pid
        self.is_connected = False
        self.writes = []
        self.bitmap_response = b"410008010000\r>"
        self.rx = SimpleNamespace(
            uuid=CAPTURE.ble_uuid("fff1"), handle=2, properties=["notify"], descriptors=[]
        )
        self.tx = SimpleNamespace(
            uuid=CAPTURE.ble_uuid("fff2"),
            handle=4,
            properties=["write-without-response"] if no_response else ["write"],
            descriptors=[],
        )
        self.services = [
            SimpleNamespace(
                uuid=CAPTURE.ble_uuid("fff0"), handle=1, characteristics=[self.rx, self.tx]
            )
        ]

    async def __aenter__(self):
        self.is_connected = True
        return self

    async def __aexit__(self, *_args):
        self.is_connected = False
        if self.callback:
            self.callback(self)

    async def start_notify(self, _rx, callback):
        self.notify = callback

    async def write_gatt_char(self, _tx, data, response):
        self.writes.append((bytes(data), response))
        command = data.decode().strip()
        if command == "0105" and self.disconnect_pid:
            self.is_connected = False
            self.callback(self)
            return
        reply = {
            "ATZ": b"ATZ\rELM327 v2.2\r>",
            "ATI": b"ELM327 v2.2\r>",
            "0100": self.bitmap_response,
            "0105": b"41057F\r>",
            "0110": b"411004D8\r>",
            "010C": b"410C1A90\r>",
            "010D": b"410D28\r>",
        }.get(command, b"OK\r>")
        for byte in reply:  # ATT fragmentation down to single bytes
            self.notify(self.rx, bytearray([byte]))
            await asyncio.sleep(0)


@unittest.skipUnless(HAS_BLEAK, "Install optional capture dependencies")
class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_raw_bytes_offsets_and_correlation(self):
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "capture"
            recorder = CAPTURE.Recorder(path, 100000)
            link = CAPTURE.Link(recorder, 1, 0.1)
            client = FakeClient(no_response=True)
            await client.start_notify(client.rx, link.receive)
            unsolicited = b"unsolicited\r>"
            link.receive(client.rx, unsolicited)
            reply = await link.request(client, client.tx, False, "0105")
            self.assertEqual(reply, b"41057F\r>")
            recorder.close()
            self.assertEqual((path / "rx.bin").read_bytes(), unsolicited + reply)
            self.assertEqual((path / "tx.bin").read_bytes(), b"0105\r")
            self.assertFalse(client.writes[0][1])
            events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
            rx = [event for event in events if event["event"] == "rx"]
            raw = (path / "rx.bin").read_bytes()
            for event in rx:
                recorded = raw[event["offset"] : event["offset"] + event["length"]]
                self.assertEqual(recorded, bytes.fromhex(event["hex"]))
            self.assertIsNone(rx[0]["command_id"])
            self.assertTrue(all("utc" in event and "elapsed_ns" in event for event in events))
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertEqual((path / "rx.bin").stat().st_mode & 0o777, 0o600)

    async def test_fixed_read_only_allowlist(self):
        with tempfile.TemporaryDirectory() as parent:
            recorder = CAPTURE.Recorder(Path(parent) / "capture", 100000)
            try:
                link = CAPTURE.Link(recorder, 1, 0.1)
                client = FakeClient()
                with self.assertRaises(ValueError):
                    await link.request(client, client.tx, True, "04")
                self.assertEqual(client.writes, [])
            finally:
                recorder.close()

    async def test_missing_prompt_and_binary_bytes_preserved(self):
        for raw in (b"41057F\r", b"\x00\xff>"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as parent:
                path = Path(parent) / "capture"
                recorder = CAPTURE.Recorder(path, 100000)
                link = CAPTURE.Link(recorder, 1, 0.02)

                class Client:
                    def __init__(self, receiver, payload):
                        self.receiver, self.payload = receiver, payload

                    async def write_gatt_char(self, *_args, **_kwargs):
                        self.receiver.receive(None, self.payload)

                with self.assertRaises((TimeoutError, ValueError)):
                    await link.request(Client(link, raw), None, False, "0105")
                recorder.close()
                self.assertEqual((path / "rx.bin").read_bytes(), raw)
                self.assertIsNone(link.future)

    async def test_reconnect_and_reinitialize_without_losing_connection_identity(self):
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "capture"
            recorder = CAPTURE.Recorder(path, 1000000)
            clients = []

            def factory(_address, disconnected_callback, timeout):
                client = FakeClient(disconnected_callback, disconnect_pid=not clients)
                clients.append(client)
                return client

            try:
                with self.assertRaises(TimeoutError):
                    async with asyncio.timeout(0.85):
                        await CAPTURE.capture(args(), recorder, factory)
            finally:
                recorder.close()
            self.assertGreaterEqual(len(clients), 2)
            self.assertTrue(all(client.writes[0][0] == b"ATZ\r" for client in clients))
            events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
            self.assertTrue(any(e["event"] == "connection_error" for e in events))
            self.assertTrue(
                any(
                    e["event"] == "response" and e["connection"] == 2 and e["command"] == "0110"
                    for e in events
                )
            )

    async def test_no_prompt_overflow_preserves_received_chunk(self):
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "capture"
            recorder = CAPTURE.Recorder(path, 100000)
            link = CAPTURE.Link(recorder, 1, 0.1)
            raw = b"X" * 4097

            class Client:
                async def write_gatt_char(self, *_args, **_kwargs):
                    link.receive(None, raw)

            with self.assertRaises(ValueError):
                await link.request(Client(), None, False, "0105")
            recorder.close()
            self.assertEqual((path / "rx.bin").read_bytes(), raw)

    async def test_metadata_limit_stops_capture(self):
        with tempfile.TemporaryDirectory() as parent:
            recorder = CAPTURE.Recorder(Path(parent) / "capture", 1)
            try:
                with self.assertRaises(CAPTURE.CaptureFatal):
                    recorder.event("rx", stream="rx.bin", raw=b"raw")
            finally:
                recorder.close()

    async def test_duration_stop_closes_and_records_reason(self):
        with tempfile.TemporaryDirectory() as parent:
            config = args()
            config.scan = False
            config.out = Path(parent) / "capture"
            config.max_mib = 1
            config.seconds = 0.02

            async def wait(_args, recorder):
                recorder.event("waiting")
                await asyncio.sleep(10)

            with patch.object(CAPTURE, "capture", wait):
                await CAPTURE.run(config)
            events = [
                json.loads(line) for line in (config.out / "events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(events[-1]["event"], "stop")
            self.assertEqual(events[-1]["reason"], "duration")

    async def test_storage_failure_is_fatal_and_short_writes_are_completed(self):
        class Partial:
            def __init__(self):
                self.result = bytearray()

            def write(self, data):
                self.result.extend(data[:1])
                return 1

        file = Partial()
        CAPTURE.Recorder.write_all(file, b"raw")
        self.assertEqual(file.result, b"raw")
        with tempfile.TemporaryDirectory() as parent:
            recorder = CAPTURE.Recorder(Path(parent) / "capture", 100000)
            try:
                with patch.object(recorder, "write_all", side_effect=OSError("Disk full")):
                    with self.assertRaises(CAPTURE.CaptureFatal):
                        recorder.event("rx", raw=b"bytes", stream="rx.bin")
            finally:
                recorder.close()

    async def test_supported_unknown_and_empty_maps_control_polling(self):
        for bitmap, expected in (
            (b"410008000000\r>", {b"0105\r"}),
            (b"NO DATA\r>", {command.encode() + b"\r" for command in CAPTURE.PIDS}),
            (b"410000000000\r>", set()),
        ):
            with self.subTest(bitmap=bitmap), tempfile.TemporaryDirectory() as parent:
                recorder = CAPTURE.Recorder(Path(parent) / "capture", 1000000)
                link = CAPTURE.Link(recorder, 1, 0.1)
                client = FakeClient()
                client.bitmap_response = bitmap
                client.is_connected = True
                await client.start_notify(client.rx, link.receive)
                try:
                    with self.assertRaises(TimeoutError):
                        async with asyncio.timeout(0.3):
                            await CAPTURE.poll(client, client.tx, True, link, args())
                finally:
                    recorder.close()
                requested = {
                    data for data, _ack in client.writes if data.decode().strip() in CAPTURE.PIDS
                }
                self.assertEqual(requested, expected)

    async def test_all_four_supported_raw_responses(self):
        with tempfile.TemporaryDirectory() as parent:
            recorder = CAPTURE.Recorder(Path(parent) / "capture", 1000000)
            link = CAPTURE.Link(recorder, 1, 0.1)
            client = FakeClient()
            client.bitmap_response = b"410008190000\r>"
            client.is_connected = True
            await client.start_notify(client.rx, link.receive)
            try:
                with self.assertRaises(TimeoutError):
                    async with asyncio.timeout(0.3):
                        await CAPTURE.poll(client, client.tx, True, link, args())
                commands = {data.decode().strip() for data, _ack in client.writes}
                self.assertTrue(set(CAPTURE.PIDS).issubset(commands))
            finally:
                recorder.close()

    async def test_priority_schedule_with_realistic_roundtrip_budget(self):
        schedule = CAPTURE.Schedule(CAPTURE.poll_periods(args()))
        now = 0.0
        samples = {command: [] for command in CAPTURE.PIDS}
        history = []
        while now < 120:
            command = schedule.choose(now, CAPTURE.PIDS)
            self.assertIsNotNone(command)
            now += 0.72  # observed ~0.62-second roundtrip + 0.1-second gap
            samples[command].append(now)
            history.append(command)
            schedule.completed(command, now)
        self.assertGreater(len(samples["0110"]) / now, 1 / 1.44)
        for channel in ("010C", "010D", "0105"):
            self.assertGreater(len(samples[channel]), 5)
        for before, after in zip(history, history[1:], strict=False):
            self.assertTrue(before == "0110" or after == "0110")
        for command in ("0105", "010C", "010D"):
            for before, after in zip(samples[command], samples[command][1:], strict=False):
                self.assertGreaterEqual(after - before, schedule.periods[command])

    async def test_profile_selection_and_support_unknown(self):
        config = args()
        client = FakeClient()
        rx, tx, ack = CAPTURE.endpoints(client.services, config.service, config.rx, config.tx)
        self.assertIs(rx, client.rx)
        self.assertIs(tx, client.tx)
        self.assertTrue(ack)
        client.services[0].characteristics = [client.rx]
        client.rx.properties += ["write-without-response"]
        rx, tx, ack = CAPTURE.endpoints(client.services, config.service, config.rx, config.tx)
        self.assertIs(rx, tx)
        self.assertFalse(ack)
        client.rx.properties = ["read"]
        with self.assertRaises(ValueError):
            CAPTURE.endpoints(client.services, config.service, config.rx, config.tx)
        self.assertEqual(CAPTURE.support_bitmap(b"410008000000\r410000010000\r>"), 0x08010000)
        self.assertEqual(CAPTURE.support_bitmap(b"410000000000\r>"), 0)
        self.assertIsNone(CAPTURE.support_bitmap(b"NO DATA\r>"))
        self.assertIsNone(CAPTURE.support_bitmap(b"410000000000\r4100ZZZZZZZZ\r>"))
        self.assertFalse(CAPTURE.init_ok("ATE0", b"NOT OK\r>"))


if __name__ == "__main__":
    unittest.main()
