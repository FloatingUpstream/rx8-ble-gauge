#!/usr/bin/env bash
# User-local downloads only: no sudo, device access, services, flash or credentials.
set -euo pipefail
umask 077
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
aux="${GAUGE_AUX:-$root/.local/aux}"
dev=0 capture=0 idf=1
usage() {
    echo "Usage: bash tools/bootstrap.sh [--dev] [--capture] [--no-idf]"
    echo "Installs pinned Python 3.12.12 and ESP-IDF v5.5.3 (ESP32-S3)."
    echo "--dev/--capture add pinned optional packages to repo/.venv."
    echo "--no-idf skips SDK/toolchain downloads. Requires uv, git and network."
}
for arg in "$@"; do
    case "$arg" in
        --dev) dev=1 ;;
        --capture) capture=1 ;;
        --no-idf) idf=0 ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
command -v uv >/dev/null || { echo "Install uv first: https://docs.astral.sh/uv/" >&2; exit 1; }
[[ "$aux" == /* ]] || { echo "GAUGE_AUX must be an absolute path" >&2; exit 2; }
export GAUGE_AUX="$aux"
export UV_PYTHON_INSTALL_DIR="$aux/python-managed"
export UV_CACHE_DIR="$aux/uv-cache"
export PIP_CACHE_DIR="$aux/pip-cache"
export PIP_NO_INPUT=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
unset UV_PYTHON_PREFERENCE
export UV_MANAGED_PYTHON=1
export UV_NO_PROGRESS=1
python_version=3.12.12
uv python install --no-bin "$python_version"
# IDF must create its own venv; install-python-env refuses a venv interpreter.
# Keep the stable tools path pointing to the actual managed Python installation.
managed_python="$(uv python find --system --managed-python --no-project "$python_version")"
managed_prefix="$("$managed_python" -c 'import sys; print(sys.prefix)')"
if [[ ! -e "$aux/python" && ! -L "$aux/python" ]]; then
    ln -s -- "$managed_prefix" "$aux/python"
fi
if [[ ! -x "$aux/python/bin/python" ]] ||
    ! "$aux/python/bin/python" -c \
        "import platform, sys; sys.exit(platform.python_version() != '$python_version' or sys.prefix != sys.base_prefix)"; then
    echo "Existing $aux/python must be a non-venv Python $python_version; move it aside and retry." >&2
    exit 1
fi
if (( idf )); then
    command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
    export IDF_PATH="$aux/sdk/esp-idf-v5.5.3"
    export IDF_TOOLS_PATH="$aux/idf-tools"
    export IDF_PYTHON_ENV_PATH="$aux/idf-python"
    commit=2c211b236707889e8400c4dc5644dd5c4ee071e0
    if [[ ! -d "$IDF_PATH" ]]; then
        mkdir -p "$(dirname "$IDF_PATH")"
        GIT_TERMINAL_PROMPT=0 git clone --branch v5.5.3 --depth 1 \
            https://github.com/espressif/esp-idf.git "$IDF_PATH"
    fi
    if [[ "$(git -C "$IDF_PATH" rev-parse HEAD)" != "$commit" ]]; then
        echo "Expected ESP-IDF v5.5.3 at $commit; checkout differs, not overwriting." >&2
        exit 1
    fi
    GIT_TERMINAL_PROMPT=0 git -C "$IDF_PATH" submodule update --init --recursive --depth 1
    export PATH="$aux/python/bin:$PATH"
    python "$IDF_PATH/tools/idf_tools.py" install --targets esp32s3
    mkdir -p "$IDF_PYTHON_ENV_PATH"
    python "$IDF_PATH/tools/idf_tools.py" install-python-env
fi
if (( dev || capture )); then
    if [[ ! -x "$root/.venv/bin/python" ]]; then
        uv venv --python "$python_version" "$root/.venv"
    fi
    if [[ "$("$root/.venv/bin/python" -c 'import platform; print(platform.python_version())')" != "$python_version" ]]; then
        echo "Existing repo/.venv must use Python $python_version; move it aside and retry." >&2
        exit 1
    fi
    requirements=()
    (( ! dev )) || requirements+=(-r "$root/requirements-dev.txt")
    (( ! capture )) || requirements+=(-r "$root/tools/requirements-capture.txt")
    uv pip install --python "$root/.venv/bin/python" \
        -c "$root/tools/constraints-tools.txt" "${requirements[@]}"
fi
echo "Bootstrap complete; no hardware or host configuration changed."
(( ! idf )) || echo "Next: source tools/idf-env.sh"
