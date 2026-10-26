#!/usr/bin/env bash
# One temporary user service owns capture and its sleep/lid inhibitor.
set -euo pipefail
umask 077
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
aux="${GAUGE_AUX:-$root/.local/aux}"
state="$aux/monitor"
unit=rx8gauge-capture.service
python="${GAUGE_PYTHON:-$root/.venv/bin/python}"
usage() {
    echo "Usage: bash tools/monitor.sh start [--address MAC] [capture options]"
    echo "       bash tools/monitor.sh stop|status|logs"
    echo "First start needs --address; later starts reuse the privately saved address."
}
case "${1:-}" in
    start)
        shift
        mkdir -p "$state"
        chmod 700 "$state"
        exec 9>"$state/lock"
        flock -x 9
        if systemctl --user is-active --quiet "$unit"; then
            echo "Capture already running; use status or stop." >&2
            exit 1
        fi
        address="${VEEPEAK_ADDRESS:-}"
        if [[ "${1:-}" == --address ]]; then
            address="${2:-}"
            [[ -n "$address" ]] || { usage; exit 2; }
            shift 2
        elif [[ -z "$address" && -f "$state/address" ]]; then
            IFS= read -r address <"$state/address" || true
        fi
        if [[ ! "$address" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
            echo "Provide --address with the actual Veepeak MAC (or VEEPEAK_ADDRESS)." >&2
            exit 2
        fi
        # Capture directory is owned by the launcher, not overridable downstream.
        for arg in "$@"; do
            case "$arg" in
                --scan|--address|--address=*|--out|--out=*)
                    echo "Use leading --address; --out/--scan are not launcher options." >&2
                    exit 2 ;;
            esac
        done
        [[ "$python" == /* && -x "$python" ]] || {
            echo "Missing interpreter: $python; run bootstrap.sh --capture or set GAUGE_PYTHON to an absolute executable path." >&2
            exit 1
        }
        out="$aux/captures/veepeak-$(date -u +%Y%m%dT%H%M%S-%NZ)"
        mkdir -p "$(dirname "$out")"
        systemd-run --user --unit="$unit" --collect --service-type=exec \
            --property=KillMode=control-group --property=TimeoutStopSec=30s \
            --property="WorkingDirectory=$root" \
            --description="RX8 raw BLE capture with temporary sleep/lid inhibition" \
            systemd-inhibit --no-ask-password --what=sleep:idle:handle-lid-switch \
            --mode=block --who=RX8-capture --why="Unattended raw BLE logging" \
            "$python" "$root/tools/capture_ble.py" --address "$address" --out "$out" "$@"
        # Directory is created by capture only after inhibition has been acquired.
        for _ in {1..50}; do
            [[ -f "$out/events.jsonl" ]] && break
            if ! systemctl --user is-active --quiet "$unit"; then
                echo "Startup failed; inspect: journalctl --user -u $unit -n 30" >&2
                exit 1
            fi
            sleep 0.1
        done
        if [[ ! -f "$out/events.jsonl" ]]; then
            systemctl --user stop "$unit" || true
            echo "Capture startup timed out; inhibitor/service stopped." >&2
            exit 1
        fi
        printf '%s\n' "$address" >"$state/address"
        printf '%s\n' "$out" >"$state/last-capture"
        echo "Running with temporary sleep/lid inhibition. Raw capture: $out"
        echo "Verify sensor replies while parked: bash tools/monitor.sh logs"
        ;;
    stop)
        mkdir -p "$state"
        chmod 700 "$state"
        exec 9>"$state/lock"
        flock -x 9
        # Missing collected unit is harmless; real manager/stop errors must propagate.
        load_state="$(systemctl --user show "$unit" --property=LoadState --value)"
        if [[ "$load_state" != not-found ]]; then
            systemctl --user stop "$unit"
        fi
        echo "Capture stopped; its sleep/lid inhibitor is released. Other inhibitors untouched."
        ;;
    status)
        systemctl --user show "$unit" --property=ActiveState --property=SubState \
            --property=MainPID 2>/dev/null || true
        [[ ! -f "$state/last-capture" ]] || printf 'Last capture: %s\n' "$(<"$state/last-capture")"
        ;;
    logs)
        exec journalctl --user -u "$unit" -n 30 -f
        ;;
    *)
        usage
        exit 2
        ;;
esac
