#!/usr/bin/env bash
# squawk-watchdog.sh — keep squawk-ws (:25147) and squawk-feed (:25135) alive.
# Runs every 60s via squawk-watchdog.timer (user systemd, additive).
# It ONLY ever starts things that are down; it never stops or restarts
# anything healthy. Safe to run alongside manual worker restarts.
#
# Why this exists (2026-09-14): both daemons "died silently" twice each.
# Root cause was never the daemons: fleet workers ran
# `pitchfork supervisor stop/start/--force` (5x on 2026-09-14), which kills
# every managed child, and the replacement supervisor was always started
# WITHOUT --boot, so boot_start daemons never came back on their own.
# pitchfork retry=true only covers crashes under a LIVE supervisor.
set -u
STATE_DIR=/home/toxic/.local/state/squawk-watchdog
LOG=$STATE_DIR/watchdog.log
LOCK=$STATE_DIR/watchdog.lock
mkdir -p "$STATE_DIR"
exec 9>"$LOCK"
flock -n 9 || exit 0  # another run in flight; skip quietly

cd /home/toxic/estate

# Resolve the pitchfork binary from the LIVE supervisor so CLI and
# supervisor can never skew versions (2.16.0 vs 2.25.0 is a known hazard).
# The same pgrep doubles as the liveness check (no CLI output parsing).
PF=/home/toxic/.local/share/mise/installs/pitchfork/latest/pitchfork
SUP_PID=""
for p in $(pgrep -f "pitchfork supervisor run" 2>/dev/null); do
  exe=$(readlink "/proc/$p/exe" 2>/dev/null || true)
  case "$exe" in *pitchfork) SUP_PID=$p; PF=$exe; break;; esac
done

log() { printf "%s %s\n" "$(date "+%F %T %Z")" "$*" >>"$LOG"; }
port_open() { python3 -c "import socket; s=socket.socket(); s.settimeout(3); s.connect((\"127.0.0.1\", $1))" 2>/dev/null; }
pf_running() { "$PF" status "$1" 2>/dev/null | grep -q "Status: running"; }

# 1. supervisor liveness — without it, nothing below can be managed.
if [ -z "$SUP_PID" ]; then
  log "ACTION supervisor not running -> pitchfork supervisor start"
  "$PF" supervisor start >>"$LOG" 2>&1
  sleep 10
fi

# 2. daemons: port must listen AND (pitchfork reports running OR the
# service health endpoint actually responds). The endpoint check covers
# pitchfork supervisor state desync (2026-09-29: supervisor stuck on
# "errored"/"stopped" for squawk-feed while the service was healthy;
# pf_running alone caused false restarts).
endpoint_ok() { curl -sf --max-time 3 "http://127.0.0.1:$1$2" >/dev/null 2>&1; }
check_daemon() {
  local name=$1 port=$2 health_path="${3:-}"
  healthy() {
    port_open "$port" || return 1
    if [ -n "$health_path" ]; then endpoint_ok "$port" "$health_path"; else pf_running "$name"; fi
  }
  if healthy; then return 0; fi
  log "ACTION $name down (port $port closed or not healthy) -> pitchfork start $name"
  "$PF" start "$name" >>"$LOG" 2>&1
  sleep 6
  if healthy; then
    log "OK $name recovered on :$port"
  else
    log "ALERT $name STILL DOWN on :$port after pitchfork start"
  fi
}

check_daemon squawk-ws 25147
check_daemon squawk-feed 25135 /squawk-feed/seq

date "+%F %T %Z" >"$STATE_DIR/heartbeat"
