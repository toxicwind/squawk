#!/bin/bash
# run-sink.sh: pitchfork launcher for the squawk-relay sink (rig-side watcher).
set -euo pipefail
export SQUAWK_RELAY_DIR="${SQUAWK_RELAY_DIR:-/home/toxic/.fleet-bus/squawk-relay}"
export SQUAWK_CHAT_ROOT="${SQUAWK_CHAT_ROOT:-/home/toxic/.fleet-bus/squawk-root}"
export FLEET_KEYS_DIR="${FLEET_KEYS_DIR:-$SQUAWK_CHAT_ROOT/keys}"
export SQUAWK_RELAY_IDENTITY="${SQUAWK_RELAY_IDENTITY:-relay}"
export SQUAWK_CODE_DIR="${SQUAWK_CODE_DIR:-/home/toxic/squawk}"
exec python3 "$SQUAWK_RELAY_DIR/sink.py"
