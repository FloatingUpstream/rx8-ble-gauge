"""Minimal read-only ELM-like TCP test server. Synthetic data, not an ECU model."""

import argparse
import asyncio
import json
import math
import time
from collections import Counter
from pathlib import Path


class Faults:
    """Process-wide deterministic fault budget, retained across reconnect/reset."""

    def __init__(self, mode="none", command="0110", every=1, after=0, count=0):
        self.mode, self.command = mode, command
        self.every, self.after, self.limit = every, after, count
        self.matches = self.injected = 0
        self.commands = Counter()

    def apply(self, command, normal):
        known = command in (
            "ATZ",
            "ATWS",
            "ATE0",
            "ATE1",
            "ATL0",
            "ATL1",
            "ATS0",
            "ATS1",
            "ATH0",
            "ATSP0",
            "ATSP6",
            "ATAT0",
            "ATAT1",
            "ATAT2",
            "ATI",
            "ATDP",
            "ATDPN",
            "ATRV",
        ) or (
            len(command) == 4
            and command.startswith("01")
            and all(c in "0123456789ABCDEF" for c in command[2:])
        )
        self.commands[command if known else "other"] += 1
        if self.mode == "none" or command != self.command:
            return normal
        self.matches += 1
        if (
            self.matches <= self.after
            or (self.matches - self.after) % self.every
            or (self.limit and self.injected >= self.limit)
        ):
            return normal
        self.injected += 1
        if self.mode == "malformed":
            return b"41 " + command[-2:].encode() + b" ZZ\r>"
        if self.mode == "wrong-pid":
            return b"41 FF 00\r>"
        if self.mode == "oversized":
            return b"X" * 600 + b"\r>"
        if self.mode == "no-prompt":
            return normal.removesuffix(b">")
        if self.mode == "silent":
            return b""
        if self.mode == "bad-status":
            return b"NOT OK\r>"
        raise ValueError(f"Unknown fault: {self.mode}")

    def save(self, path):
        if path:
            target = Path(path)
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_text(
                json.dumps({"commands": dict(self.commands), "injected": self.injected}) + "\n"
            )
            temporary.replace(target)


def pid_number(raw):
    try:
        pid = int(raw, 16)
        if not 1 <= pid <= 255 or pid % 32 == 0:
            raise ValueError
        return pid
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Expected a hex data PID (01..FF, not a bitmap PID)"
        ) from None


def add_simulation_options(parser):
    parser.add_argument(
        "--scenario", choices=["normal", "cold", "hot", "no-data"], default="normal"
    )
    parser.add_argument("--unsupported-pid", type=pid_number, action="append", default=[])
    parser.add_argument(
        "--fault",
        choices=[
            "none",
            "malformed",
            "wrong-pid",
            "oversized",
            "no-prompt",
            "silent",
            "bad-status",
        ],
        default="none",
    )
    parser.add_argument("--fault-command", default="0110")
    parser.add_argument("--fault-every", type=int, default=1)
    parser.add_argument("--fault-after", type=int, default=0)
    parser.add_argument("--fault-count", type=int, default=0, help="0 = unlimited")
    parser.add_argument("--metrics", help="Atomic JSON command counts, updated after commands")


def faults_from_args(args):
    return Faults(
        getattr(args, "fault", "none"),
        "".join(getattr(args, "fault_command", "0110").upper().split()),
        getattr(args, "fault_every", 1),
        getattr(args, "fault_after", 0),
        getattr(args, "fault_count", 0),
    )


def validate_fault_args(parser, args):
    if args.fault_every < 1 or args.fault_after < 0 or args.fault_count < 0:
        parser.error("fault-every must be positive; fault-after/count must be nonnegative")


class ElmSession:
    def __init__(self, scenario="normal", clock=time.monotonic, unsupported_pids=(), faults=None):
        self.scenario = scenario
        self.clock = clock
        self.started = clock()
        self.echo = True
        self.linefeeds = True
        self.spaces = True
        self.unsupported_pids = set(unsupported_pids)
        self.faults = faults

    def sample(self):
        seconds = self.clock() - self.started
        cycle = (1 + math.sin(seconds / 8)) / 2
        coolant = {"normal": 87, "cold": 20, "hot": 110, "no-data": 87}[self.scenario]
        samples = {
            0x05: bytes([coolant + 40]),
            0x0C: round((850 + 5150 * cycle) * 4).to_bytes(2, "big"),
            0x0D: bytes([round(100 * cycle)]),
            0x0F: bytes([28 + 40]),
            0x10: round((4 + 96 * cycle) * 100).to_bytes(2, "big"),
            0x42: (13900).to_bytes(2, "big"),
        }
        return {pid: value for pid, value in samples.items() if pid not in self.unsupported_pids}

    @staticmethod
    def support_bitmap(start, supported):
        bits = sum(1 << (32 - (pid - start)) for pid in supported if start < pid <= start + 32)
        return bits.to_bytes(4, "big")

    def reply(self, raw):
        normal = self.normal_reply(raw)
        return self.faults.apply("".join(raw.upper().split()), normal) if self.faults else normal

    def normal_reply(self, raw):
        command = "".join(raw.upper().split())
        echo = self.echo
        if command in ("ATZ", "ATWS"):
            self.echo = self.linefeeds = self.spaces = True
            answer = "ELM327 v1.5 (RX8 TEST SIM)"
        elif command in ("ATE0", "ATE1", "ATL0", "ATL1", "ATS0", "ATS1"):
            attr = {"E": "echo", "L": "linefeeds", "S": "spaces"}[command[2]]
            setattr(self, attr, command[3] == "1")
            answer = "OK"
        elif command in ("ATH0", "ATSP0", "ATSP6", "ATAT0", "ATAT1", "ATAT2"):
            answer = "OK"
        elif command == "ATI":
            answer = "ELM327 v1.5 (RX8 TEST SIM)"
        elif command == "ATDP":
            answer = "ISO 15765-4 (CAN 11/500)"
        elif command == "ATDPN":
            answer = "A6"
        elif command == "ATRV":
            answer = "13.9V"
        elif command.startswith("01") and len(command) == 4:
            try:
                pid = int(command[2:], 16)
            except ValueError:
                pid = -1
            samples = self.sample()
            supported = set(samples) | {0x20, 0x40}
            if pid in (0, 0x20, 0x40):
                payload = self.support_bitmap(pid, supported)
            else:
                payload = samples.get(pid)
            if payload is None or self.scenario == "no-data":
                answer = "NO DATA"
            else:
                answer = (bytes([0x41, pid]) + payload).hex(" ").upper()
                if not self.spaces:
                    answer = answer.replace(" ", "")
        else:
            answer = "?"
        newline = "\r\n" if self.linefeeds else "\r"
        return ((raw + newline if echo else "") + answer + newline + ">").encode(
            "ascii", errors="replace"
        )


async def serve_client(reader, writer, args):
    session = ElmSession(
        args.scenario,
        unsupported_pids=getattr(args, "unsupported_pid", ()),
        faults=getattr(args, "faults", None),
    )
    pending = bytearray()
    writer.write(b">")
    await writer.drain()
    try:
        while data := await reader.read(256):
            for byte in data:
                if byte == 10:  # ignore LF from CRLF clients
                    continue
                if byte != 13:
                    pending.append(byte)
                    if len(pending) > 128:
                        return  # bounded command buffer
                    continue
                raw = pending.decode("ascii", errors="replace")
                pending.clear()
                await asyncio.sleep(args.delay_ms / 1000)
                response = session.reply(raw)
                if session.faults:
                    session.faults.save(getattr(args, "metrics", None))
                size = args.fragment_bytes or max(1, len(response))
                for offset in range(0, len(response), size):
                    writer.write(response[offset : offset + size])
                    await writer.drain()
                    if args.fragment_bytes:
                        await asyncio.sleep(0.01)
    except (ConnectionError, BrokenPipeError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


async def run(args):
    args.faults = faults_from_args(args)
    server = await asyncio.start_server(lambda r, w: serve_client(r, w, args), args.host, args.port)
    print(f"Synthetic ELM TCP simulator: {args.host}:{args.port}, {args.scenario}", flush=True)
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=35000)
    add_simulation_options(parser)
    parser.add_argument("--delay-ms", type=int, default=20)
    parser.add_argument("--fragment-bytes", type=int, default=0)
    args = parser.parse_args()
    validate_fault_args(parser, args)
    if args.delay_ms < 0 or args.fragment_bytes < 0:
        parser.error("delay and fragment size must be nonnegative")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
