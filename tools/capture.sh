#!/usr/bin/env bash
set -euo pipefail
umask 077
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
aux="${GAUGE_AUX:-$root/.local/aux}"
camera="${GAUGE_CAMERA:-}"
if [[ "${1:-}" == --camera ]]; then
    camera="${2:-}"
    [[ $# -ge 2 ]] || { echo "--camera needs a device path" >&2; exit 2; }
    shift 2
fi
if [[ $# -gt 1 || -z "$camera" || "$camera" == -* ]]; then
    echo "Usage: bash tools/capture.sh [--camera /dev/videoN] [output.jpg]" >&2
    echo "Alternatively set GAUGE_CAMERA. Set GAUGE_CAMERA_CONTROLS=1 to tune UVC controls." >&2
    exit 2
fi
output="${1:-$aux/captures/device-$(date -u +%Y%m%dT%H%M%S-%NZ).jpg}"
mkdir -p "$(dirname "$output")"

# Keep capture open while applying controls; some UVC controls reset on open.
ffmpeg -n -hide_banner -loglevel error -f v4l2 -input_format mjpeg \
    -video_size 1920x1080 -framerate 30 -i "$camera" \
    -vf 'select=gte(n\,150)' -frames:v 1 -update 1 "$output" &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
if [[ "${GAUGE_CAMERA_CONTROLS:-0}" == 1 ]]; then
    sleep 1
    v4l2-ctl -d "$camera" --set-ctrl=auto_exposure=1
    v4l2-ctl -d "$camera" --set-ctrl="exposure_time_absolute=${GAUGE_CAMERA_EXPOSURE:-30},gain=0"
    v4l2-ctl -d "$camera" --set-ctrl=focus_automatic_continuous=0
    sleep 0.3
    v4l2-ctl -d "$camera" --set-ctrl="focus_absolute=${GAUGE_CAMERA_FOCUS:-110}"
fi
wait "$pid"
trap - EXIT
echo "$output"
