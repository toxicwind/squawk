#!/usr/bin/env bash
# run-tail.sh -- pitchfork entry for the nats-tail daemon (Taps, 2026-09-21).
# Ensures the venv (nats-py) exists, then execs the dual-publish tailer.
set -euo pipefail
VENV="/home/toxic/.local/share/squawk-nats/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q nats-py
fi
exec "$VENV/bin/python" "$(dirname "$0")/squawk_nats_tail.py"
