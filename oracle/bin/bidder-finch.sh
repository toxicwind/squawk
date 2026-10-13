#!/bin/bash
# bidder-finch launcher - started by pitchfork
set -euo pipefail
# IDEMPOTENT (2026-09-29): if another instance is already running, exit 0
# quietly instead of crashing on the flock. The pitchfork supervisor can
# spawn duplicate retries when its state desyncs; duplicates must be no-ops.
if pgrep -f "bidder.py --id finch" >/dev/null 2>&1; then
  exit 0
fi
exec /usr/bin/python3 /home/toxic/estate/ranch/squawk/oracle/bin/bidder.py \
  --id finch \
  --name Finch \
  --emoji "\U0001F426" \
  --tags "forensics,verify,research,probe" \
  --tagline "I verify what others claim and dig till the evidence talks. Point me at the uncertain thing."
