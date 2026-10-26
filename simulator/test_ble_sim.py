"""Optional BLE frontend tests without requiring a Bluetooth radio."""

import asyncio
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HAS_BLESS = importlib.util.find_spec("bless") is not None
if HAS_BLESS:
    import ble_sim


class FakeServer:
    def __init__(self):
        self.characteristics = {}
        self.fragments = []
        self.started = asyncio.Event()
        self.stopped = False

    async def add_new_service(self, uuid):
        self.service = uuid

    async def add_new_characteristic(self, service, uuid, properties, value, permissions):
        self.characteristics[uuid] = SimpleNamespace(
            uuid=uuid, value=value, properties=properties, permissions=permissions
        )

    async def start(self):
        self.started.set()

    async def stop(self):
        self.stopped = True

    def get_characteristic(self, uuid):
        return self.characteristics[uuid]

    def update_value(self, service, uuid):
        self.fragments.append(bytes(self.characteristics[uuid].value))
        return True


@unittest.skipUnless(HAS_BLESS, "Optional Bless dependencies not installed")
class BleFrontendTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, scenario, expected, profile="split", **options):
        server = FakeServer()
        args = SimpleNamespace(
            scenario=scenario, delay_ms=0, fragment_bytes=3, profile=profile, **options
        )
        with patch.object(ble_sim, "BlessServer", return_value=server):
            task = asyncio.create_task(ble_sim.run(args))
            try:
                await asyncio.wait_for(server.started.wait(), 1)
                self.assertEqual(server.service, ble_sim.SERVICE)
                tx = server.get_characteristic(ble_sim.RX if profile == "single" else ble_sim.TX)
                if profile == "no-response":
                    self.assertFalse(tx.properties & ble_sim.GATTCharacteristicProperties.write)
                    self.assertTrue(
                        tx.properties & ble_sim.GATTCharacteristicProperties.write_without_response
                    )
                # Command split across ATT writes; CR is the command boundary.
                server.write_request_func(tx, b"010")
                server.write_request_func(tx, b"5\r")
                async with asyncio.timeout(2):
                    while not b"".join(server.fragments).endswith(b">"):
                        await asyncio.sleep(0.01)
                self.assertIn(expected, b"".join(server.fragments))
                self.assertTrue(all(1 <= len(fragment) <= 3 for fragment in server.fragments))
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(server.stopped)

    async def test_fragmented_command_and_notifications(self):
        await self.exercise("normal", b"41 05 7F")

    async def test_no_data(self):
        await self.exercise("no-data", b"NO DATA")

    async def test_single_characteristic(self):
        await self.exercise("normal", b"41 05 7F", profile="single")

    async def test_write_without_response_only(self):
        await self.exercise("normal", b"41 05 7F", profile="no-response")

    async def test_fault_injection(self):
        await self.exercise("normal", b"ZZ", fault="malformed", fault_command="0105")

    async def test_incompatible_profiles(self):
        for profile in ("wrong-service", "no-notify", "no-write"):
            with self.subTest(profile=profile):
                server = FakeServer()
                args = SimpleNamespace(
                    scenario="normal", delay_ms=0, fragment_bytes=3, profile=profile
                )
                with patch.object(ble_sim, "BlessServer", return_value=server):
                    task = asyncio.create_task(ble_sim.run(args))
                    try:
                        await asyncio.wait_for(server.started.wait(), 1)
                        if profile == "wrong-service":
                            self.assertNotEqual(server.service, ble_sim.SERVICE)
                        elif profile == "no-notify":
                            self.assertFalse(
                                server.get_characteristic(ble_sim.RX).properties
                                & ble_sim.GATTCharacteristicProperties.notify
                            )
                        else:
                            self.assertFalse(
                                server.get_characteristic(ble_sim.TX).properties
                                & ble_sim.GATTCharacteristicProperties.write
                            )
                    finally:
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    self.assertTrue(server.stopped)
