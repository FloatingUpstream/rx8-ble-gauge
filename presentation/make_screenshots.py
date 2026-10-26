"""Capture real shared-UI fixtures and compose the README gallery.

Build the desktop app first. Gallery rasterisation additionally uses
`rsvg-convert` (Ubuntu: librsvg2-bin; Arch: librsvg). No car/radio is accessed.
"""

import argparse
import base64
import os
import shutil
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=root / "desktop/build/gauge_desktop")
    parser.add_argument("--out", type=Path, default=root / "docs/images")
    parser.add_argument("--force", action="store_true", help="Replace generated artwork")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("coolant", "Coolant priority", ["--scenario", "normal"]),
        ("maf", "MAF priority", ["--scenario", "normal", "--maf"]),
        ("stale", "No stale readings", ["--scenario", "stale"]),
        ("adapters", "Adapter selection", ["--picker"]),
    ]
    files = [args.out / f"{name}.png" for name, _, _ in fixtures]
    files += [args.out / "ui-gallery.svg", args.out / "ui-gallery.png"]
    if not args.force and any(file.exists() for file in files):
        parser.error("Output already exists; use --force to replace generated screenshots")
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="450" viewBox="0 0 1440 450">',
        '<rect width="1440" height="450" rx="20" fill="#101722"/>',
        '<g font-family="DejaVu Sans,sans-serif">',
        '<text x="28" y="29" font-size="13" letter-spacing="1.5" fill="#8dc4ce">'
        "ONE SHARED UI · SYNTHETIC DESKTOP FIXTURES</text>",
    ]
    for index, (name, label, options) in enumerate(fixtures):
        path = args.out / f"{name}.png"
        subprocess.run(
            [str(args.app.resolve()), *options, "--snapshot", str(path.resolve())],
            env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
            check=True,
            timeout=20,
        )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        x = 24 + 352 * index
        svg.extend(
            [
                f'<rect x="{x}" y="46" width="336" height="360" rx="14" fill="#192332"/>',
                f'<text x="{x + 168}" y="77" text-anchor="middle" font-size="18" '
                f'fill="#edf3f8">{label}</text>',
                f'<clipPath id="screen{index}">'
                f'<circle cx="{x + 168}" cy="240" r="140"/></clipPath>',
                f'<image x="{x + 28}" y="100" width="280" height="280" '
                f'clip-path="url(#screen{index})" href="data:image/png;base64,{encoded}"/>',
                f'<circle cx="{x + 168}" cy="240" r="140" fill="none" stroke="#35445b"/>',
            ]
        )
    svg.extend(
        [
            '<text x="28" y="432" font-size="13" fill="#9eacbc">'
            "LVGL · 360 × 360 logical pixels · screenshots, not vehicle measurements</text>",
            "</g></svg>",
        ]
    )
    source = args.out / "ui-gallery.svg"
    source.write_text("\n".join(svg) + "\n")
    renderer = shutil.which("rsvg-convert")
    if renderer:
        subprocess.run([renderer, str(source), "-o", str(args.out / "ui-gallery.png")], check=True)
    else:
        print("Individual PNGs and gallery SVG created; install rsvg-convert for gallery PNG.")
    print(f"Synthetic screenshots: {args.out}")


if __name__ == "__main__":
    main()
