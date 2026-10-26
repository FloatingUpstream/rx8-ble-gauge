#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python="${GAUGE_TEST_PYTHON:-}"
if [[ -z "$python" ]]; then
    if [[ -x "$root/.venv/bin/python" ]]; then
        python="$root/.venv/bin/python"
    else
        python=python3
    fi
fi
bash "$root/tools/build-desktop.sh"
"$python" -m unittest discover -s "$root/tests" -v
