#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
aux="${GAUGE_AUX:-$root/.local/aux}"
lvgl="$aux/upstream/lvgl"
commit=85aa60d18b3d5e5588d7b247abf90198f07c8a63
if [[ ! -d "$lvgl/.git" ]]; then
    mkdir -p "$aux/upstream"
    git clone --depth 1 --branch v9.5.0 https://github.com/lvgl/lvgl.git "$lvgl"
fi
if [[ "$(git -C "$lvgl" rev-parse HEAD)" != "$commit" ]]; then
    echo "Expected LVGL 9.5.0 at $commit; upstream checkout differs." >&2
    exit 1
fi
build="${GAUGE_DESKTOP_BUILD:-$root/desktop/build}"
cmake -S "$root/desktop" -B "$build" -G Ninja -DLVGL_SOURCE_DIR="$lvgl" "$@"
cmake --build "$build" --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
ctest --test-dir "$build" --output-on-failure
