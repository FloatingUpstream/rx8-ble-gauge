#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
port="${1:-${GAUGE_PORT:-}}"
if [[ $# -gt 1 || -z "$port" || "$port" == -* ]]; then
    echo "Usage: bash tools/flash.sh /dev/serial/by-id/YOUR_DEVICE (or set GAUGE_PORT)" >&2
    exit 2
fi
source "$root/tools/idf-env.sh"
trap 'python "$root/tools/normalize_lock.py"' EXIT
if [[ ! -r "$port" || ! -w "$port" ]]; then
    echo "Serial port missing or inaccessible: $port" >&2
    exit 1
fi
idf.py -C "$root/firmware" build
cd "$root/firmware/build"
# This board needed watchdog_reset to leave manually entered download mode.
python -m esptool --chip esp32s3 --port "$port" -b 460800 \
    --before "${GAUGE_FLASH_BEFORE:-usb_reset}" --after watchdog_reset \
    write_flash @flash_args
