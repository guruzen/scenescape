#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# One lifecycle entrypoint for WSL2/Linux. Python is part of the prerequisites.
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'python3 is required.' >&2; exit 1; }
case "${1:-}" in
  recover-legacy-data|seed-native-data|repair-native-media)
    exec python3 "${ROOT_DIR}/tools/native_data.py" "$1"
    ;;
  *)
    exec python3 "${ROOT_DIR}/tools/native_runtime.py" "$@"
    ;;
esac
