#!/usr/bin/env bash
# rig-validate.sh
# Validates the integrity of the Pens rig structure.

set -e

ESTATE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEAVER_DIR="$ESTATE_ROOT/agents/weaver"
MARKET_LOOP_SRC="$WEAVER_DIR/bin/market-loop.ts"
MARKET_LOOP_LINK="$ESTATE_ROOT/agents/weaver/bin/market-loop.ts"

echo "=== Rig Validation ==="

# Check 1: Weaver directory exists
if [ ! -d "$WEAVER_DIR" ]; then
    echo "FAIL: Weaver directory missing at $WEAVER_DIR"
    exit 1
fi
echo "OK: Weaver directory exists."

# Check 2: Market loop symlink/file exists
if [ ! -e "$MARKET_LOOP_LINK" ]; then
    echo "FAIL: Market loop link missing at $MARKET_LOOP_LINK"
    exit 1
fi
echo "OK: Market loop link exists."

# Check 3: Market loop is executable or readable
if [ ! -r "$MARKET_LOOP_LINK" ]; then
    echo "FAIL: Market loop is not readable."
    exit 1
fi
echo "OK: Market loop is readable."

# Check 4: Delend CLI tools exist
TOOLS=("delend-oracle" "delend-iterate" "delend-experimental" "delend-code-race" "rig-create")
for tool in "${TOOLS[@]}"; do
    if [ ! -x "$ESTATE_ROOT/bin/$tool" ]; then
        echo "WARN: Tool $tool is not executable or missing."
    else
        echo "OK: Tool $tool is executable."
    fi
done

echo "=== Validation Complete ==="
