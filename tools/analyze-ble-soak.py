#!/usr/bin/env python3
"""Assess application telemetry in same-boot BLE soak logs, not upstream internals."""

import argparse
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    parser.add_argument(
        "--steady-from-ms",
        type=int,
        required=True,
        help="Firmware uptime at the start of the deliberate-fault-free phase",
    )
    parser.add_argument("--min-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.min_seconds <= 0 or args.steady_from_ms < 0:
        parser.error("min-seconds must be positive and steady-from-ms nonnegative")
    text = "".join(path.read_text(errors="replace") for path in args.logs)
    samples = [
        tuple(map(int, match))
        for match in re.findall(
            r"I \((\d+)\) gauge_ble: ELM link=(\d+) coolant=(-?\d+) valid=([01]) "
            r"MAF_centi=(\d+) valid=([01]) support=(\d+)/(\d+)",
            text,
        )
    ]
    steady = [s for s in samples if s[0] >= args.steady_from_ms]
    disconnects = [
        {"ms": int(ms), "reason": int(reason)}
        for ms, reason in re.findall(r"\((\d+)\) gauge_ble: Disconnected: reason=(\d+)", text)
    ]
    bad = [s for s in steady if s[1] != 1 or s[3] != 1 or s[5] != 1 or s[6:] != (1, 1)]
    duration = (steady[-1][0] - steady[0][0]) / 1000 if steady else 0
    max_gap = max((b[0] - a[0] for a, b in zip(steady, steady[1:], strict=False)), default=0)
    heaps = [
        tuple(map(int, match))
        for match in re.findall(r"\((\d+)\) rx8gauge: .*free internal=(\d+), PSRAM=(\d+)", text)
        if int(match[0]) >= args.steady_from_ms
    ]
    unexpected = [event for event in disconnects if event["ms"] >= args.steady_from_ms]
    panics = re.findall(r"Guru Meditation|panic'ed|abort\(\)|assert failed|Brownout detector", text)
    resets = text.count("ESP-ROM:")
    monotonic = all(b[0] > a[0] for a, b in zip(samples, samples[1:], strict=False))
    passed = (
        duration >= args.min_seconds
        and bool(steady)
        and not bad
        and not unexpected
        and not panics
        and resets <= 1
        and monotonic
        and max_gap <= 10000
    )
    report = {
        "passed": passed,
        "steady_seconds": duration,
        "steady_samples": len(steady),
        "invalid_steady_samples": len(bad),
        "max_sample_gap_ms": max_gap,
        "steady_disconnects": unexpected,
        "all_disconnects": disconnects,
        "panic_or_brownout_messages": panics,
        "rom_start_count": resets,
        "sample_uptime_monotonic": monotonic,
        "first_steady_heap": heaps[0] if heaps else None,
        "last_steady_heap": heaps[-1] if heaps else None,
        "note": "Steady phase must exclude operator-controlled faults. Heap observations "
        "are not proof of leak absence; actual adapter/car compatibility is separate.",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"BLE steady phase: {'PASS' if passed else 'FAIL'}, {duration:.1f}s, "
        f"{len(steady)} samples, {len(unexpected)} disconnects; {args.output}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
