#!/usr/bin/env bash
# Audible request for hands-on assistance. No desktop configuration changes.
set -euo pipefail
args=()
[[ -z "${GAUGE_AUDIO_SINK:-}" ]] || args+=("--device=$GAUGE_AUDIO_SINK")
paplay "${args[@]}" /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga
