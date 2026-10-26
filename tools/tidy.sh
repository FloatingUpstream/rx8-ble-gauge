#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$root/tools/idf-env.sh"
trap 'python "$root/tools/normalize_lock.py"' EXIT
if ! command -v clang-tidy >/dev/null || [[ "$(command -v clang-tidy)" != "$IDF_TOOLS_PATH/"* ]]; then
    echo "Install ESP Clang: python \$IDF_PATH/tools/idf_tools.py install esp-clang" >&2
    exit 1
fi
# A separate Clang configuration avoids polluting the GCC production build.
IDF_TOOLCHAIN=clang idf.py -C "$root/firmware" -B "$root/firmware/build/tidy" \
    -D "SDKCONFIG=$root/firmware/build/tidy/sdkconfig" reconfigure
dirs=("$root/firmware/main" "$root/ui" "$root/protocol")
[[ ! -d "$root/firmware/components" ]] || dirs+=("$root/firmware/components")
while IFS= read -r -d '' file; do
    clang-tidy -p "$root/firmware/build/tidy" "$file"
done < <(find "${dirs[@]}" -type f \( -name '*.c' -o -name '*.cpp' \) -print0)
