#!/usr/bin/env python3
"""Unattended, read-only ELM BLE capture: unchanged RX/TX bytes and JSONL timing."""

import argparse
import asyncio
import datetime
import json
import math
import os
import re
import signal
import time
import uuid
from pathlib import Path

from bleak import BleakClient, BleakScanner

INIT = ("ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0", "ATI")
PIDS = ("0110", "0105", "010C", "010D")
ALLOWED = {*INIT, "0100", *PIDS}


def poll_periods(args):
    return {
        "0110": 0.0,  # MAF gets spare bandwidth, not a promised sample rate.
        "0105": getattr(args, "coolant_period", 10.0),
        "010C": getattr(args, "rpm_period", 5.0),
        "010D": getattr(args, "speed_period", 5.0),
    }


class Schedule:
    """At most one auxiliary request between MAF requests; no catch-up bursts."""

    def __init__(self, periods):
        self.periods = periods
        self.due = dict.fromkeys(periods, 0.0)
        self.last = None

    def choose(self, now, enabled):
        auxiliary = [cmd for cmd in enabled if cmd != "0110" and now >= self.due[cmd]]
        if "0110" in enabled and (self.last != "0110" or not auxiliary):
            return "0110"
        return min(auxiliary, key=lambda cmd: self.due[cmd]) if auxiliary else None

    def completed(self, command, now):
        self.last = command
        self.due[command] = now + self.periods[command]


class CaptureFatal(Exception):
    """Do not retry when evidence cannot be recorded."""


def ble_uuid(value):
    if re.fullmatch(r"[0-9a-fA-F]{4}", value):
        value = f"0000{value}-0000-1000-8000-00805f9b34fb"
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a 16-bit or full BLE UUID") from None


class Recorder:
    def __init__(self, directory, max_bytes):
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.started = time.monotonic_ns()
        self.seq = self.total = 0
        self.max_bytes = max_bytes
        self.closed = False
        self.files = {}
        try:
            for name in ("rx.bin", "tx.bin", "events.jsonl"):
                descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                self.files[name] = os.fdopen(descriptor, "wb", buffering=0)
        except OSError:
            self.close()
            raise

    def event(self, kind, *, raw=None, stream=None, **fields):
        if self.closed:
            raise CaptureFatal("Capture has already closed")
        event = {
            "seq": self.seq,
            "utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "elapsed_ns": time.monotonic_ns() - self.started,
            "event": kind,
            **fields,
        }
        if raw is not None:
            event.update(
                file=stream, offset=self.files[stream].tell(), length=len(raw), hex=raw.hex()
            )
        line = (json.dumps(event, separators=(",", ":")) + "\n").encode()
        size = len(line) + (len(raw) if raw is not None else 0)
        if self.total + size > self.max_bytes:
            raise CaptureFatal("Capture size limit reached; stopping rather than dropping bytes")
        try:
            if raw is not None:
                self.write_all(self.files[stream], raw)
            self.write_all(self.files["events.jsonl"], line)
        except OSError as error:
            raise CaptureFatal(f"Cannot save capture: {error}") from error
        self.seq += 1
        self.total += size

    @staticmethod
    def write_all(file, data):
        remaining = memoryview(data)
        while remaining:
            count = file.write(remaining)
            if not count:
                raise OSError("Short capture write")
            remaining = remaining[count:]

    def close(self):
        if self.closed:
            return
        self.closed = True
        for file in self.files.values():
            try:
                os.fsync(file.fileno())
            finally:
                file.close()


def endpoints(services, service_uuid, rx_uuid, tx_uuid):
    matches = [service for service in services if service.uuid == service_uuid]
    if len(matches) != 1:
        raise ValueError("Expected exactly one selected ELM service")
    chars = matches[0].characteristics

    def find(identifier):
        found = [char for char in chars if char.uuid == identifier]
        if len(found) > 1:
            raise ValueError("Ambiguous characteristic UUID")
        return found[0] if found else None

    rx = find(rx_uuid)
    tx = find(tx_uuid)
    if rx is None or "notify" not in rx.properties:
        raise ValueError("Selected RX characteristic does not support notifications")
    if tx is None:
        tx = rx
    if not {"write", "write-without-response"}.intersection(tx.properties):
        raise ValueError("Selected TX characteristic is not writable")
    return rx, tx, "write" in tx.properties


def service_tree(services):
    return [
        {
            "uuid": service.uuid,
            "handle": service.handle,
            "characteristics": [
                {
                    "uuid": char.uuid,
                    "handle": char.handle,
                    "properties": char.properties,
                    "descriptors": [
                        {"uuid": descriptor.uuid, "handle": descriptor.handle}
                        for descriptor in char.descriptors
                    ],
                }
                for char in service.characteristics
            ],
        }
        for service in services
    ]


def support_bitmap(response):
    bitmap = None
    for line in re.split(rb"[\r\n>]", response):
        compact = b"".join(line.split()).upper()
        if not compact.startswith(b"4100"):
            continue
        if not re.fullmatch(rb"4100[0-9A-F]{8}", compact):
            return None
        value = int(compact[4:], 16)
        bitmap = value if bitmap is None else bitmap | value
    return bitmap


def init_ok(command, response):
    lines = [line.strip().upper() for line in re.split(rb"[\r\n>]", response)]
    if command not in ("ATZ", "ATI"):
        return b"OK" in lines
    return any(re.fullmatch(rb"(ELM327|STN[0-9]{4,})(\s.*)?", line) for line in lines)


class Link:
    def __init__(self, recorder, connection, timeout):
        self.recorder, self.connection, self.timeout = recorder, connection, timeout
        self.future = None
        self.command_id = 0
        self.buffer = bytearray()
        self.fatal = None

    def disconnected(self, _client):
        if self.future is not None and not self.future.done():
            self.future.set_exception(ConnectionError("BLE link disconnected"))

    def receive(self, _characteristic, data):
        raw = bytes(data)
        try:
            self.recorder.event(
                "rx",
                raw=raw,
                stream="rx.bin",
                connection=self.connection,
                command_id=self.command_id if self.future is not None else None,
                pending=self.future is not None and not self.future.done(),
            )
            for byte in raw:
                if self.future is None or self.future.done():
                    break
                self.buffer.append(byte)
                if len(self.buffer) > 4096:
                    self.future.set_exception(ValueError("ELM response exceeds 4096 bytes"))
                elif byte == 62:  # >
                    self.future.set_result(bytes(self.buffer))
                elif byte > 126 or (byte < 32 and byte not in (9, 10, 13)):
                    self.future.set_exception(ValueError("Non-ASCII ELM response"))
        except CaptureFatal as error:
            self.fatal = error
            if self.future is not None and not self.future.done():
                self.future.set_exception(error)

    async def request(self, client, tx, acknowledged, command):
        if command not in ALLOWED:
            raise ValueError("Only fixed adapter setup and read-only Mode 01 commands are allowed")
        if self.fatal:
            raise self.fatal
        if self.future is not None:
            raise RuntimeError("Only one command may be outstanding")
        self.command_id += 1
        self.buffer.clear()
        self.future = asyncio.get_running_loop().create_future()
        raw = (command + "\r").encode("ascii")
        try:
            self.recorder.event(
                "tx_attempt",
                raw=raw,
                stream="tx.bin",
                command=command,
                connection=self.connection,
                command_id=self.command_id,
                acknowledged=acknowledged,
            )
            async with asyncio.timeout(self.timeout):
                await client.write_gatt_char(tx, raw, response=acknowledged)
                self.recorder.event(
                    "write_returned", connection=self.connection, command_id=self.command_id
                )
                response = await self.future
            self.recorder.event(
                "response",
                connection=self.connection,
                command_id=self.command_id,
                command=command,
                hex=response.hex(),
            )
            return response
        finally:
            if not self.future.done():
                self.future.cancel()
            elif not self.future.cancelled():
                self.future.exception()  # retrieve errors even if the write failed first
            self.future = None


async def poll(client, tx, acknowledged, link, args):
    for command in INIT:
        response = await link.request(client, tx, acknowledged, command)
        if not init_ok(command, response):
            raise ValueError(f"ELM verification/setup failed at {command}")
        await asyncio.sleep(0.02)
    link.recorder.event("elm_verified", connection=link.connection)
    bitmap = None
    discovery_at = 0.0
    display_at = 0.0
    schedule = Schedule(poll_periods(args))
    probed = False
    seen = set()
    while client.is_connected:
        if link.fatal:
            raise link.fatal
        enabled = [
            command
            for command in PIDS
            if bitmap is None or bitmap & (1 << (32 - int(command[2:], 16)))
        ]
        if time.monotonic() >= discovery_at and (
            not probed or not enabled or set(enabled).issubset(seen)
        ):
            bitmap = support_bitmap(await link.request(client, tx, acknowledged, "0100"))
            probed = True
            seen.clear()
            link.recorder.event(
                "support",
                connection=link.connection,
                bitmap_hex=f"{bitmap:08x}" if bitmap is not None else None,
            )
            discovery_at = time.monotonic() + (30 if bitmap is not None else 2)
            enabled = [
                command
                for command in PIDS
                if bitmap is None or bitmap & (1 << (32 - int(command[2:], 16)))
            ]
            if bitmap is not None and enabled:
                discovery_at = math.inf
        command = schedule.choose(time.monotonic(), enabled)
        if command is not None:
            await asyncio.sleep(args.gap)
            response = await link.request(client, tx, acknowledged, command)
            schedule.completed(command, time.monotonic())
            seen.add(command)
            if time.monotonic() >= display_at:
                print(f"{command}: {response[:120]!r}", flush=True)
                display_at = time.monotonic() + 5
        else:
            await asyncio.sleep(0.2)
    raise ConnectionError("BLE link disconnected")


async def capture(args, recorder, client_factory=BleakClient):
    connection = 0
    while True:
        connection += 1
        link = Link(recorder, connection, args.timeout)
        recorder.event("connect_attempt", connection=connection, address=args.address)
        try:
            async with client_factory(
                args.address,
                disconnected_callback=link.disconnected,
                timeout=args.timeout,
            ) as client:
                recorder.event(
                    "connected", connection=connection, services=service_tree(client.services)
                )
                rx, tx, acknowledged = endpoints(client.services, args.service, args.rx, args.tx)
                recorder.event(
                    "profile",
                    connection=connection,
                    rx_handle=rx.handle,
                    tx_handle=tx.handle,
                    acknowledged=acknowledged,
                )
                await client.start_notify(rx, link.receive)
                # Record/discard any subscription-time banner before associating ATZ.
                await asyncio.sleep(0.15)
                print(f"Connected: {args.address}; recording raw MAF/coolant/RPM/speed", flush=True)
                await poll(client, tx, acknowledged, link, args)
        except CaptureFatal:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as error:
            recorder.event(
                "connection_error",
                connection=connection,
                error_type=type(error).__name__,
                error=str(error),
            )
            print(f"Link {connection}: {error}; reconnecting in {args.retry:g}s", flush=True)
        await asyncio.sleep(args.retry)


async def run(args):
    if args.scan:
        found = await BleakScanner.discover(timeout=5, return_adv=True)
        for address, (device, adv) in sorted(found.items()):
            print(address, adv.local_name or device.name or "(unnamed)", adv.service_uuids)
        return
    recorder = Recorder(args.out, args.max_mib * 1024 * 1024)
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, task.cancel)
    try:
        recorder.event(
            "start",
            schema=1,
            address=args.address,
            service=args.service,
            rx=args.rx,
            tx=args.tx,
            seconds=args.seconds,
            gap=args.gap,
            timeout=args.timeout,
            poll_periods=poll_periods(args),
            allowed_commands=sorted(ALLOWED),
            note="RX unchanged. TX records attempts, not proof of ECU receipt. Timestamps "
            "are laptop receipt times, not ECU sampling times. No decoded CSV.",
        )
        print(
            f"Capture: {args.out}; stop with Ctrl-C (automatic stop in {args.seconds:g}s)",
            flush=True,
        )
        try:
            async with asyncio.timeout(args.seconds):
                await capture(args, recorder)
        except TimeoutError:
            recorder.event("stop", reason="duration")
        except asyncio.CancelledError:
            recorder.event("stop", reason="signal")
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)
        recorder.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan", action="store_true", help="List nearby devices without connecting"
    )
    parser.add_argument("--address", help="Explicit BLE address; no name-based automatic selection")
    parser.add_argument("--service", type=ble_uuid, default=ble_uuid("fff0"))
    parser.add_argument("--rx", type=ble_uuid, default=ble_uuid("fff1"))
    parser.add_argument("--tx", type=ble_uuid, default=ble_uuid("fff2"))
    parser.add_argument("--seconds", type=float, default=7200)
    parser.add_argument("--gap", type=float, default=0.1, help="Seconds between PID requests")
    parser.add_argument(
        "--coolant-period",
        type=float,
        default=10,
        help="Minimum seconds after a coolant reply until its next request",
    )
    parser.add_argument("--rpm-period", type=float, default=5)
    parser.add_argument("--speed-period", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--retry", type=float, default=2)
    parser.add_argument("--max-mib", type=int, default=256)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            os.environ.get("GAUGE_AUX", Path(__file__).resolve().parents[1] / ".local" / "aux")
        )
        / "captures"
        / f"veepeak-{stamp}",
    )
    args = parser.parse_args()
    if not args.scan and not args.address:
        parser.error("Select --scan or provide --address")
    if (
        any(
            not math.isfinite(value) or value <= 0
            for value in (
                args.seconds,
                args.gap,
                args.timeout,
                args.retry,
                args.coolant_period,
                args.rpm_period,
                args.speed_period,
            )
        )
        or args.max_mib < 1
    ):
        parser.error("Durations/gap and max-mib must be finite and positive")
    try:
        asyncio.run(run(args))
    except (CaptureFatal, OSError) as error:
        parser.exit(1, f"Capture stopped: {error}\n")


if __name__ == "__main__":
    main()
