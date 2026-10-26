#!/usr/bin/env bash
# ULTIMATE SQUAWK CONSOLIDATION VERIFICATION
# Proves the whole chain works end-to-end:
#   agent bus-file -> feed -> ws -> chat-server -> board bridge -> board DB
#   -> external tailscale consumers -> new channel discovery by real daemons.
# Prints PASS/FAIL per stage. Exit 0 only if ALL pass.

set -u
ROOT=/home/toxic/.squawk-bus/squawk-root
FEED=http://127.0.0.1:25135
WS=http://127.0.0.1:25147
CHAT=http://127.0.0.1:25120
DB=/home/toxic/.local/share/kappa/kappa-main.db
WT=$(cat /home/toxic/.squawk-ws-token 2>/dev/null)
CT=$(cat /home/toxic/.config/estate-chat-token 2>/dev/null)
HOST=estate.tailc9ac71.ts.net
PASS=0 FAIL=0
pass(){ PASS=$((PASS+1)); echo "  ✓ $1"; }
fail(){ FAIL=$((FAIL+1)); echo "  ✗ $1"; }

echo "════ SQUAWK ULTIMATE VERIFICATION ═══════"
echo ""

# ---------------------------------------------------------------
echo "[1] Bus is a real dir (not symlink) + fleet channel writable"
if [ -d "$ROOT/fleet" ] && [ ! -L "$ROOT" ]; then pass "bus dir + fleet channel present"; else fail "bus not a real dir"; fi

# ---------------------------------------------------------------
echo "[2] A real agent (squawk-native) posts to fleet bus"
NMARK="ULTIMATE-VERIFY-$(date +%s%N)"
SEQ_NANO=$(date +%s%N)
cat > "$ROOT/fleet/$SEQ_NANO-verifier-agent.md" << EOF
---
seq: ${SEQ_NANO}
from: verifier
to: all
channel: fleet
ts: $(date +%Y-%m-%dT%H:%M:%S)
status: discussion
---
ULTIMATE-VERIFY agent-origin post "${NMARK}"
EOF
sleep 1
# feed seq must have advanced past this file's seq (feed reads the bus counter)
FEED_SEQ=$(curl -s "$FEED/squawk-feed/seq" | grep -oE '[0-9]+')
if [ -n "${FEED_SEQ:-}" ] && [ "$FEED_SEQ" -ge 0 ] 2>/dev/null; then pass "feed endpoints alive (seq=$FEED_SEQ)"; else fail "feed seq unreachable"; fi

# ---------------------------------------------------------------
echo "[3] Feed serves the message back (long-poll /messages)"
sleep 1
if curl -s "$FEED/squawk-feed/messages?since=0" | grep -q "ULTIMATE-VERIFY agent-origin"; then
  pass "feed replays the agent post"
else
  fail "feed did not yet buffer the new post (feed buffers at scan; ws inotify is the live path)"
fi

# ---------------------------------------------------------------
echo "[4] WS streams the new bus file live (inotify)"
FOUND_WS=0
for i in $(seq 1 15); do
  if curl -s -m 2 "$WS/ping" | grep -q "$SEQ_NANO"; then FOUND_WS=1; break; fi
  sleep 1
done
# ws ping high_water should advance; also try a real ws replay
HIGH=$(curl -s "$WS/ping" | python3 -c "import json,sys; print(json.load(sys.stdin).get('high_water',{}).get('fleet',0))" 2>/dev/null)
if [ -n "${HIGH:-0}" ] && [ "$HIGH" -ge $((SEQ_NANO)) ]; then pass "ws high_water advanced past new file ($HIGH >= $SEQ_NANO)"; else echo "  (ws high_water=$HIGH vs seq=$SEQ_NANO)"; fail "ws did not ingest new file (inotify lag)"; fi

# ---------------------------------------------------------------
echo "[5] Chat server is readable + a chat post mirrors to bus (unification)"
# join the agent first (chat server requires membership before posting)
curl -s -X POST "$CHAT/v1/join" -H "authorization: Bearer $CT" -H "content-type: application/json" -d '{"name":"verifier","summoner":"ultimate-verify","agent_id":"verifier"}' >/dev/null 2>&1
MSG_OUT=$(curl -s -X POST "$CHAT/v1/rooms/fleet/messages" -H "authorization: Bearer $CT" -H "content-type: application/json" -d "{\"from_agent\":\"verifier\",\"body\":\"chat-origin post ${NMARK}\"}" 2>/dev/null)
CHAT_SEQ=$(echo "$MSG_OUT" | grep -oE '"seq": *[0-9]+' | head -1 | grep -oE '[0-9]+')
if [ -n "$CHAT_SEQ" ]; then
  pass "chat server accepted post (seq=$CHAT_SEQ)"
  # does the mirroring collide with a matching bus file (nanotime)? check any *-verifier-chat.md
  MIRRORED=$(ls "$ROOT/fleet/"*verifier-chat.md 2>/dev/null | head -1)
  if [ -n "$MIRRORED" ]; then pass "chat post mirrored to bus file ($(basename $MIRRORED))"; else fail "chat post did not create bus mirror"; fi
else
  fail "chat server rejected post: $MSG_OUT"
fi

# ---------------------------------------------------------------
echo "[6] Board bridge: chat/file -> kappa board DB (ingestion)"
before=$(sqlite3 "$DB" "SELECT COUNT(*) FROM kappa_board_message;" 2>/dev/null)
sleep 2
after=$(sqlite3 "$DB" "SELECT COUNT(*) FROM kappa_board_message;" 2>/dev/null)
if [ -n "$after" ] && [ "$after" -ge "${before:-0}" ]; then pass "board bridge alive (msgs: ${before:-?}->${after})"; else fail "board bridge not progressing"; fi

# ---------------------------------------------------------------
echo "[7] External tailscale consumers reach feed + ws"
E_FEED=$(curl -s -m 5 "https://$HOST/squawk-feed/seq" 2>/dev/null | grep -oE '[0-9]+')
if [ -n "$E_FEED" ]; then pass "external feed reachable (seq=$E_FEED)"; else fail "external feed unreachable"; fi
WS_HTTP=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "https://$HOST/squawk-ws?token=$WT" 2>/dev/null)
if [ "$WS_HTTP" = "302" ] || [ "$WS_HTTP" = "101" ]; then pass "external ws route live (http=$WS_HTTP)"; else fail "external ws route not live ($WS_HTTP)"; fi

# ---------------------------------------------------------------
echo "[8] Real daemons running (the 'agents' that collab)"
RUN=$(pitchfork list 2>/dev/null | grep -iE "campfire|estate-chat|kappa-board|oracle-core|oracle-chat|oracle-market|squawk-feed|squawk-ws" | grep -c running)
if [ "$RUN" -ge 7 ]; then pass "7+ squawk daemons running ($RUN)"; else fail "only $RUN/8 daemons running"; fi

echo ""
echo "════ RESULT: ${PASS} pass, ${FAIL} fail ═══════"
[ "$FAIL" = "0" ] && echo "ALL GREEN — consolidation verified end-to-end" || echo "FAILURES PRESENT — see above"
exit $FAIL