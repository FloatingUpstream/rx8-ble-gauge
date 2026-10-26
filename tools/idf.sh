#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$root/tools/idf-env.sh"
trap 'python "$root/tools/normalize_lock.py"' EXIT
idf.py "$@"
