import asyncio
import unittest
from types import SimpleNamespace

from elm_sim import ElmSession, Faults, serve_client


class ElmTests(unittest.TestCase):
    def session(self, scenario="normal"):
        session = ElmSession(scenario, clock=lambda: 0)
        session.reply("ATE0")
        session.reply("ATL0")
        return session

    def test_coolant(self):
        self.assertEqual(self.session().reply("0105"), b"41 05 7F\r>")
        self.assertEqual(self.session("cold").reply("0105"), b"41 05 3C\r>")
        self.assertEqual(self.session("hot").reply("0105"), b"41 05 96\r>")

    def test_scaling(self):
        session = self.session()
        self.assertEqual(session.reply("010C"), b"41 0C 35 84\r>")  # 3425 RPM
        self.assertEqual(session.reply("0110"), b"41 10 14 50\r>")  # 52 g/s
        self.assertEqual(session.reply("0142"), b"41 42 36 4C\r>")

    def test_supported_pids(self):
        session = self.session()
        bitmap = session.support_bitmap(0, set(session.sample()) | {0x20, 0x40})
        self.assertTrue(int.from_bytes(bitmap, "big") & (1 << 27))  # PID 05
        self.assertEqual(session.reply("0140"), b"41 40 40 00 00 00\r>")

    def test_unsupported_and_unknown_are_distinct(self):
        session = ElmSession(clock=lambda: 0, unsupported_pids=[0x10])
        session.reply("ATE0")
        session.reply("ATL0")
        self.assertEqual(session.reply("0110"), b"NO DATA\r>")
        bitmap = session.support_bitmap(0, set(session.sample()))
        self.assertFalse(int.from_bytes(bitmap, "big") & (1 << 16))
        self.assertTrue(int.from_bytes(bitmap, "big") & (1 << 27))
        self.assertNotIn(b"NO DATA", session.reply("0100"))
        self.assertEqual(self.session("no-data").reply("0100"), b"NO DATA\r>")

    def test_fault_budgets_survive_reset_and_reconnect(self):
        faults = Faults("malformed", every=2, after=1, count=2)
        session = ElmSession(clock=lambda: 0, faults=faults)
        replies = [session.reply("0110") for _ in range(7)]
        self.assertEqual(sum(b"ZZ" in reply for reply in replies), 2)
        session.reply("ATZ")
        session = ElmSession(clock=lambda: 0, faults=faults)
        self.assertNotIn(b"ZZ", session.reply("0110"))
        self.assertEqual(faults.injected, 2)

    def test_fault_payloads(self):
        for mode in ("malformed", "wrong-pid", "oversized", "no-prompt", "silent", "bad-status"):
            with self.subTest(mode=mode):
                faults = Faults(mode)
                session = ElmSession(clock=lambda: 0, faults=faults)
                reply = session.reply("0110")
                self.assertEqual(faults.injected, 1)
                if mode in ("no-prompt", "silent"):
                    self.assertNotIn(b">", reply)
                if mode == "oversized":
                    self.assertGreater(len(reply), 512)

    def test_missing_and_bad_commands(self):
        self.assertEqual(self.session("no-data").reply("0105"), b"NO DATA\r>")
        self.assertEqual(self.session().reply("01FF"), b"NO DATA\r>")
        self.assertEqual(self.session().reply("01ZZ"), b"NO DATA\r>")
        self.assertEqual(self.session().reply("04"), b"?\r>")  # no DTC clear

    def test_formatting_and_reset(self):
        session = self.session()
        session.reply("ATS0")
        self.assertEqual(session.reply("01 05"), b"41057F\r>")
        session.reply("ATZ")
        self.assertEqual(session.reply("0105"), b"0105\r\n41 05 7F\r\n>")


class TcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_commands_and_responses(self):
        args = SimpleNamespace(scenario="normal", delay_ms=0, fragment_bytes=2)
        server = await asyncio.start_server(lambda r, w: serve_client(r, w, args), "127.0.0.1", 0)
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.sockets[0].getsockname()[1]
            )
            try:

                async def response():
                    return await asyncio.wait_for(reader.readuntil(b">"), timeout=2)

                self.assertEqual(await response(), b">")
                writer.write(b"ATE0\r\nATL0\r")
                await writer.drain()
                self.assertIn(b"OK", await response())
                self.assertIn(b"OK", await response())
                writer.write(b"01")
                await writer.drain()
                await asyncio.sleep(0.01)
                writer.write(b"05\r")
                await writer.drain()
                self.assertEqual(await response(), b"41 05 7F\r>")
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
