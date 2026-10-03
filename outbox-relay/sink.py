#!/usr/bin/env python3
"""squawk-relay sink: rig-side watcher -> outbox.jsonl (transactional record).

Design (transactional outbox, Richardson): the outbox is the durable record.
Every new channel message gets a global monotonic seq + deterministic
idempotency key, appended with fsync BEFORE the per-channel cursor advances.
At-least-once by construction; the forwarder deduplicates on the key.

- Source of truth per channel: `chat.py relay-out` (the signed machine
  contract: signature verification, sealed-message flagging).
- Honors control.json: paused holds everything (cursors frozen, nothing
  lost); channels allowlists; skip_authors avoids echo loops (notably the
  forwarder's own posts as `relay`).
- Sealed messages: NEVER unsealed here. Flagged sealed:true with title only.

Lane: main d23c8a01. pitchfork daemon: squawk-relay-sink.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay_common as C

TEXT_CAP = 2000
FULL_SWEEP_INTERVAL = 60.0
DEBOUNCE = 1.0
SINK_SEEN_CAP = 10000  # broker-style dedup window (Kafka: last N per producer)


def load_control():
    ctl = C.load_json(C.CONTROL, {})
    return {
        "paused": bool(ctl.get("paused", False)),
        "channels": ctl.get("channels"),
        "skip_authors": set(ctl.get("skip_authors", ["relay", "squawk-relay"])),
    }


def load_state():
    st = C.load_json(C.SINK_STATE, {})
    if "feed_seq" not in st:
        st["feed_seq"] = 0
    if "channels" not in st:
        st["channels"] = {}
    if "invalid_sig_skipped" not in st:
        st["invalid_sig_skipped"] = 0
    return st


def relay_out(channel, since):
    """Run the signed machine contract; return (records, cursor)."""
    cmd = [sys.executable, str(C.CHAT_PY), "--root", str(C.CHAT_ROOT),
           "relay-out", channel, "--since", str(since),
           "--identity", C.RELAY_IDENTITY]
    env = dict(os.environ)
    env["FLEET_KEYS_DIR"] = str(C.KEYS_DIR)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    if p.returncode != 0:
        raise RuntimeError("relay-out %s failed rc=%d: %s" % (channel, p.returncode, p.stderr.strip()[-500:]))
    records, cursor = [], since
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "cursor" in obj and "seq" not in obj:
            cursor = max(cursor, int(obj["cursor"]))
        else:
            records.append(obj)
    return records, cursor


def commit_state(state):
    # strip transient _-prefixed keys (sets etc.): not JSON-safe
    clean = {k: v for k, v in state.items() if not k.startswith("_")}
    C.atomic_write_json(C.SINK_STATE, clean)


def outbox_keys():
    """Idempotency keys already in the log (for broker-level dedup)."""
    keys = set()
    try:
        with open(C.OUTBOX) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    k = C.derive_key(json.loads(line))
                    if k:
                        keys.add(k)
                except (ValueError, AttributeError):
                    continue
    except OSError:
        pass
    return keys


def seed_sink_seen(state):
    """Seed the sink's dedup set from state + the outbox log itself.

    Kafka-broker style: the log is the dedup authority. Even after a
    cursor rewind or state loss, an already-logged key is never appended
    twice. Capped to SINK_SEEN_CAP newest.
    """
    seen = set(state.get("sink_seen", [])) | outbox_keys()
    state["_sink_seen_set"] = seen
    state["sink_seen"] = sorted(seen)[-SINK_SEEN_CAP:]
    state.setdefault("sink_dup_suppressed", 0)


def outbox_max_seq():
    """Max seq physically present in the outbox (0 when empty/missing)."""
    mx = 0
    try:
        with open(C.OUTBOX) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    mx = max(mx, int(json.loads(line).get("seq", 0)))
                except (ValueError, AttributeError):
                    continue
    except OSError:
        pass
    return mx


def reconcile_seq(state):
    """feed_seq = max(state, outbox max): never reuse a seq after a crash,
    restart, or an external append (e.g. test re-injection). Idempotent;
    called on startup and before every sweep."""
    mx = outbox_max_seq()
    if mx > state["feed_seq"]:
        C.log("seq reconcile: feed_seq %d -> %d (outbox max)" % (state["feed_seq"], mx))
        state["feed_seq"] = mx
    return state["feed_seq"]


def append_outbox(entry, state):
    """Append one entry with fsync, then bump the global seq (atomic state)."""
    state["feed_seq"] += 1
    entry["seq"] = state["feed_seq"]
    entry["ingest_ts"] = C.now_iso()
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    C.OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(C.OUTBOX, "a") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    return entry


def sweep_channel(channel, state, ctl):
    cursor = int(state["channels"].get(channel, 0))
    try:
        records, top = relay_out(channel, cursor)
    except Exception as e:
        C.log("sweep %s failed (will retry): %s" % (channel, e))
        return 0
    new_count = 0
    for rec in records:
        msg_seq = int(rec.get("seq", 0))
        if msg_seq <= cursor:
            continue
        author = rec.get("from", "unknown")
        if author in ctl["skip_authors"]:
            cursor = max(cursor, msg_seq)
            continue
        sealed = bool(rec.get("sealed"))
        body = rec.get("body") or ""
        if sealed:
            text = "[sealed message: %s]" % (rec.get("title") or "sealed")
            body_sig = "sealed:" + (rec.get("title") or "")
        else:
            text = body[:TEXT_CAP]
            body_sig = body[:500]
        entry = {
            "idempotency_key": C.idempotency_key(
                channel, msg_seq, author, rec.get("ts", ""), body_sig),
            "ts": rec.get("ts", ""),
            "channel": channel,
            "author": author,
            "to": rec.get("to", "all"),
            "title": rec.get("title", ""),
            "text": text,
            "msg_seq": msg_seq,
            "sealed": sealed,
            "sig": rec.get("signature", "unknown"),
            "lamport": rec.get("lamport", 0),
        }
        key = entry["idempotency_key"]
        if key in state["_sink_seen_set"]:
            # broker-level dedup (Kafka idempotent-producer style): the key
            # is already in the log; do not append a second copy. Cursor
            # still advances so a rewind never replays it.
            state["sink_dup_suppressed"] = state.get("sink_dup_suppressed", 0) + 1
            C.log("sink dup suppressed key=%s msg_seq=%d" % (key, msg_seq))
        else:
            append_outbox(entry, state)
            state["_sink_seen_set"].add(key)
            state["sink_seen"] = (state.get("sink_seen", []) + [key])[-SINK_SEEN_CAP:]
            new_count += 1
            C.log("outbox seq=%d key=%s #%s@%s msg_seq=%d" % (
                entry["seq"], key, channel, author, msg_seq))
        cursor = max(cursor, msg_seq)
        state["channels"][channel] = cursor
        commit_state(state)  # atomic (seq, cursor): crash replays <=1 msg
    if top != state["channels"].get(channel, 0):
        state["channels"][channel] = max(top, cursor)
        commit_state(state)
    return new_count


def sweep_all(state, ctl):
    if ctl["paused"]:
        C.log("paused: holding (cursors frozen)")
        return 0
    reconcile_seq(state)  # never reuse a seq, even after external appends
    total = 0
    only = ctl["channels"]
    for d in C.channel_dirs():
        if only and d.name not in only:
            continue
        total += sweep_channel(d.name, state, ctl)
    return total


def main():
    C.acquire_lock("sink")
    state = load_state()
    reconcile_seq(state)
    seed_sink_seen(state)  # broker-level dedup seeded from the log itself
    commit_state(state)  # persist the reconciled seq before ingesting
    C.log("sink starting: root=%s dest(n/a) feed_seq=%d" % (C.CHAT_ROOT, state["feed_seq"]))
    watch_paths = [d for d in C.channel_dirs()] + [C.RELAY_DIR]
    try:
        ino = C.Inotify(watch_paths)
        C.log("inotify watching %d paths" % len(watch_paths))
    except OSError as e:
        C.log("inotify unavailable (%s); poll fallback" % e)
        ino = None
    last_full = 0.0
    while True:
        ctl = load_control()
        try:
            if ino and ino.wait(5.0):
                time.sleep(DEBOUNCE)
                sweep_all(state, ctl)
                last_full = time.monotonic()
            elif time.monotonic() - last_full >= FULL_SWEEP_INTERVAL:
                sweep_all(state, ctl)
                last_full = time.monotonic()
        except Exception as e:
            C.log("sweep error (retrying): %r" % e)
            time.sleep(5.0)


if __name__ == "__main__":
    main()
