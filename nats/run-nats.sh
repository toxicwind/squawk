#!/usr/bin/env bash
# run-nats.sh -- pitchfork entry for the nats daemon (Taps, 2026-09-21).
#
# Renders nats-server.conf from nats-server.conf.template using the canonical
# squawk feed token (same secret the feed server and UI already use), then
# execs nats-server. The token never lands in the repo: the rendered config
# is 0600 under /home/toxic/.local/share/nats/.
#
# Token precedence mirrors squawk_feed.py: $SQUAWK_FEED_TOKEN first, then the
# canonical token file. The feed server owns token creation -- if neither
# exists we fail loudly instead of inventing a second secret.
set -euo pipefail

TOKEN_FILE="${SQUAWK_FEED_TOKEN_FILE:-/home/toxic/.fleet-bus/squawk-relay/feed-token}"
if [[ -n "${SQUAWK_FEED_TOKEN:-}" ]]; then
  TOKEN="$SQUAWK_FEED_TOKEN"
elif [[ -f "$TOKEN_FILE" ]]; then
  TOKEN="$(cat "$TOKEN_FILE")"
else
  echo "run-nats.sh: no feed token at $TOKEN_FILE (feed server owns token creation)" >&2
  exit 1
fi
# single-line URL-safe base64 shape guard (rejects newlines / injection)
TOKEN="$(printf '%s' "$TOKEN" | tr -d '\r\n')"
[[ "$TOKEN" =~ ^[A-Za-z0-9_-]{16,128}$ ]] || { echo "run-nats.sh: token has unexpected shape" >&2; exit 1; }

CONF_DIR="/home/toxic/.local/share/nats"
mkdir -p "$CONF_DIR/jetstream"
TEMPLATE="$(dirname "$0")/nats-server.conf.template"
[[ -f "$TEMPLATE" ]] || { echo "run-nats.sh: missing $TEMPLATE" >&2; exit 1; }
sed "s/@FEED_TOKEN@/$TOKEN/g" "$TEMPLATE" > "$CONF_DIR/nats-server.conf"
chmod 600 "$CONF_DIR/nats-server.conf"

exec /usr/bin/nats-server -c "$CONF_DIR/nats-server.conf"
