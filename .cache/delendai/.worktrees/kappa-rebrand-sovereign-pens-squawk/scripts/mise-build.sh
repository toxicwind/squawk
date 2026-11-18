#!/usr/bin/env bash
# Direct build entry: mise owns the toolchain; mbx-cache restores eligible task outputs.
set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
BUILD_CMD=$(cat <<'BUILD'
/usr/bin/python3.14 -m pytest tests -q
BUILD
)
exec "$ROOT/scripts/mise-build.sh" "squawk" "$ROOT/squawk" "$BUILD_CMD"
