#!/usr/bin/env bash
# Optional explicit host change, once per boot. Never invoked by bootstrap.
# No broad device grants, setuid executable, sudoers entry or permanent config.
set -euo pipefail
serial="${1:-}"
if [[ $# -ne 1 || ! "$serial" =~ ^[[:alnum:]:._-]+$ ]]; then
    echo "Usage: sudo bash tools/install-device-access.sh YOUR_USB_SERIAL" >&2
    echo "Only that Espressif 303a:1001 device gets active-session access until reboot." >&2
    exit 2
fi
if [[ "$EUID" != 0 ]]; then
    echo "Explicit root authorization required; rerun with sudo if desired." >&2
    exit 1
fi
rule="$(mktemp)"
trap 'rm -f "$rule"' EXIT
printf 'SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", ATTRS{idProduct}=="1001", ATTRS{serial}=="%s", TAG+="uaccess"\n' "$serial" >"$rule"
install -d -o root -g root -m 0755 /run/udev/rules.d
install -o root -g root -m 0644 "$rule" \
    /run/udev/rules.d/70-rx8gauge.rules
udevadm control --reload-rules
echo "Installed boot-local device access rule (removed on host reboot)."
echo "Replug that USB device to apply; no other devices were triggered."
