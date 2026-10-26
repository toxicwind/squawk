#!/bin/bash
# bidder-vesper launcher - started by pitchfork
set -euo pipefail
# 2026-10-19 (osprey rekey): one-shot executor route 1 (cuttinggate :25200)
# needs its own client key. Reference the inherited vault key by name so no
# literal secret is ever committed to git.
if [ -z "${ONE_SHOT_API_KEY:-}" ] && [ -n "${CUTTINGGATE_CLIENT_KEY:-}" ]; then
  export ONE_SHOT_API_KEY="$CUTTINGGATE_CLIENT_KEY"
fi
# IDEMPOTENT (mirrors bidder-forge.sh): if another instance is already
# running, exit 0 quietly instead of crashing on the flock.
if pgrep -f 'bidder.py --id vesper' >/dev/null 2>&1; then
  exit 0
fi
exec /usr/bin/python3 /home/toxic/estate/ranch/squawk/oracle/bin/bidder.py   --id vesper   --name Vesper   --emoji '🦇'   --tags 'probe,verify'   --tagline 'Vesper here — evening shepherd. I watch the lanes and verify what matters.'
