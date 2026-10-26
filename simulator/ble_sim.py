"""Synthetic ELM BLE peripheral. Advertises RX8-ELM-SIM, never a real adapter."""

import argparse
import asyncio
import logging

from bless import (
    BlessServer,
    GATTAttributePermissions,
    GATTCharacteristicProperties,
)
from elm_sim import (
    ElmSession,
    add_simulation_options,
    faults_from_args,
    validate_fault_args,
)

SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
RX = "0000fff1-0000-1000-8000-00805f9b34fb"
TX = "0000fff2-0000-1000-8000-00805f9b34fb"


async def run(args):
    profile = getattr(args, "profile", "split")
    service = SERVICE if profile != "wrong-service" else "0000ffe0-0000-1000-8000-00805f9b34fb"
    tx_uuid = RX if profile == "single" else TX
    queue = asyncio.Queue(maxsize=64)
    server = BlessServer(name="RX8-ELM-SIM")
    session = ElmSession(
        args.scenario,
        unsupported_pids=getattr(args, "unsupported_pid", ()),
        faults=faults_from_args(args),
    )
    pending = bytearray()

    def on_write(characteristic, value, **_kwargs):
        if characteristic.uuid.lower() != tx_uuid:
            return
        try:
            queue.put_nowait(bytes(value))
        except asyncio.QueueFull:
            logging.error("BLE input queue full; dropping input")

    server.write_request_func = on_write
    server.read_request_func = lambda characteristic: characteristic.value
    await server.add_new_service(service)
    rx_properties = GATTCharacteristicProperties.read
    rx_permissions = GATTAttributePermissions.readable
    if profile != "no-notify":
        rx_properties |= GATTCharacteristicProperties.notify
    if profile == "single":
        rx_properties |= (
            GATTCharacteristicProperties.write | GATTCharacteristicProperties.write_without_response
        )
        rx_permissions |= GATTAttributePermissions.writeable
    await server.add_new_characteristic(
        service,
        RX,
        rx_properties,
        bytearray(),
        rx_permissions,
    )
    if profile != "single":
        tx_properties = GATTCharacteristicProperties.write_without_response
        if profile != "no-response":
            tx_properties |= GATTCharacteristicProperties.write
        if profile == "no-write":
            tx_properties = GATTCharacteristicProperties.read
        await server.add_new_characteristic(
            service,
            TX,
            tx_properties,
            bytearray(),
            GATTAttributePermissions.readable
            if profile == "no-write"
            else GATTAttributePermissions.writeable,
        )
    await server.start()
    print(f"SIMULATED BLE ELM: RX8-ELM-SIM, {args.scenario}, profile={profile}", flush=True)
    try:
        while True:
            data = await queue.get()
            for byte in data:
                if byte == 10:
                    continue
                if byte != 13:
                    pending.append(byte)
                    if len(pending) > 128:
                        pending.clear()
                        logging.error("Oversized command discarded")
                    continue
                command = pending.decode("ascii", errors="replace")
                pending.clear()
                await asyncio.sleep(args.delay_ms / 1000)
                response = session.reply(command)
                session.faults.save(getattr(args, "metrics", None))
                print(f"{command!r} -> {response!r}", flush=True)
                # Default ATT MTU 23: at most 20 payload bytes per notification.
                for offset in range(0, len(response), args.fragment_bytes):
                    server.get_characteristic(RX).value = bytearray(
                        response[offset : offset + args.fragment_bytes]
                    )
                    server.update_value(service, RX)
                    await asyncio.sleep(0.02)
    finally:
        await server.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_simulation_options(parser)
    parser.add_argument(
        "--profile",
        choices=["split", "single", "no-response", "wrong-service", "no-notify", "no-write"],
        default="split",
    )
    parser.add_argument("--delay-ms", type=int, default=20)
    parser.add_argument("--fragment-bytes", type=int, default=3)
    args = parser.parse_args()
    validate_fault_args(parser, args)
    if args.delay_ms < 0 or not 1 <= args.fragment_bytes <= 20:
        parser.error("delay must be nonnegative; BLE fragment size must be 1..20")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
