#!/bin/bash
# bidder-scout launcher - started by pitchfork
set -euo pipefail
# IDEMPOTENT (2026-09-29): if another instance is already running, exit 0
# quietly instead of crashing on the flock. The pitchfork supervisor can
# spawn duplicate retries when its state desyncs; duplicates must be no-ops.
if pgrep -f "bidder.py --id scout" >/dev/null 2>&1; then
  exit 0
fi
exec /usr/bin/python3 /home/toxic/estate/projects/range/ranch/oracle/bin/bidder.py \
  --id scout \
  --name Scout \
  --emoji "🔭" \
  --tags "probe,research,docs" \
  --tagline "I go first, look around, and report back. If it's unknown territory, I'm already halfway there!"
