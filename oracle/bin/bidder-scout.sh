#!/bin/bash
# bidder-scout launcher - started by pitchfork
set -euo pipefail
# 2026-10-19 (osprey rekey): one-shot executor route 1 (cuttinggate :25200)
# needs its own client key. Reference the inherited vault key by name so no
# literal secret is ever committed to git.
if [ -z "${ONE_SHOT_API_KEY:-}" ] && [ -n "${CUTTINGGATE_CLIENT_KEY:-}" ]; then
  export ONE_SHOT_API_KEY="$CUTTINGGATE_CLIENT_KEY"
fi
# IDEMPOTENT (2026-09-29): if another instance is already running, exit 0
# quietly instead of crashing on the flock. The pitchfork supervisor can
# spawn duplicate retries when its state desyncs; duplicates must be no-ops.
if pgrep -f "bidder.py --id scout" >/dev/null 2>&1; then
  exit 0
fi
exec /usr/bin/python3 /home/toxic/estate/ranch/squawk/oracle/bin/bidder.py \
  --id scout \
  --name Scout \
  --emoji "🔭" \
  --tags "probe,research,docs" \
  --tagline "I go first, look around, and report back. If it's unknown territory, I'm already halfway there!"
