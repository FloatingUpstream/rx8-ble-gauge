#!/usr/bin/env bash
# Source this file, or use idf.sh. Machine-specific SDK paths stay outside Git.
_gauge_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export GAUGE_ROOT="$_gauge_root"
export GAUGE_AUX="${GAUGE_AUX:-$_gauge_root/.local/aux}"
export IDF_PATH="$GAUGE_AUX/sdk/esp-idf-v5.5.3"
export IDF_TOOLS_PATH="$GAUGE_AUX/idf-tools"
export IDF_PYTHON_ENV_PATH="$GAUGE_AUX/idf-python"
if [[ ! -f "$IDF_PATH/export.sh" || ! -x "$GAUGE_AUX/python/bin/python" ||
      ! -x "$IDF_PYTHON_ENV_PATH/bin/python" ]]; then
    echo "Missing isolated SDK/Python environment; run: bash tools/bootstrap.sh" >&2
    return 1
fi
export PATH="$GAUGE_AUX/python/bin:$PATH"
source "$IDF_PATH/export.sh"
unset _gauge_root
