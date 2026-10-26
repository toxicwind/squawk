#!/usr/bin/env bash
# run-history.sh -- pitchfork entry for the squawk-history daemon (Pry, 2026-10-19).
# Paged + compacted history reads over JetStream (:25152). Ensures the venv.
set -euo pipefail
VENV="/home/toxic/.local/share/squawk-nats/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q nats-py
fi
export SQUAWK_NATS_CHANNELS="${SQUAWK_NATS_CHANNELS:-fleet,leads,ops,estate-chat,bid-market,uitest,fleet-misfiled-20261003}"
exec "$VENV/bin/python" "$(dirname "$0")/squawk_history.py"
