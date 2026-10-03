#!/usr/bin/env python3
"""squawk-relay forwarder: outbox.jsonl -> main chat (at-least-once, idempotent, ordered).

Delivery: each outbox entry is posted to the DEST channel (default: fleet,
the main chat) through chat_commands._post_message -- the exact signed post
path the squawk CLI uses (seq lock, DAG parents, Lamport tick, HMAC-SHA256
by the relay identity). The post carries frontmatter:
    from: relay, relayed_from: squawk:<channel>, human: <author>,
    relay_key: <idempotency_key>
so every relayed message is attributable and traceable to its outbox entry.

Idempotency (effectively-exactly-once into the channel):
- persistent seen-set of idempotency keys + cursor, committed atomically
  AFTER each successful post;
- startup reconciliation: scan the dest channel for relay_key values already
  posted, so a crash between post and commit can never double-post;
- replays carrying a previously-seen key are skipped ("dup suppressed").

Ordering: entries are forwarded in global seq order; a failed post blocks
the queue (retried next sweep) and poison entries are quarantined after
MAX_ATTEMPTS so one bad entry can never stall the relay.

Loop safety: the sink honors control.json skip_authors (relay,
squawk-relay), so the forwarder's own posts are never re-ingested.

Lane: main d23c8a01. pitchfork daemon: squawk-relay-forward.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay_common as C

MAX_ATTEMPTS = 5
SEEN_CAP = 10000
SWEEP_INTERVAL = 30.0
DEBOUNCE = 1.0
RELAY_KEY_RE = re.compile(r"^relay_key:\s*(\S+)\s*$", re.M)


def load_state():
    st = C.load_json(C.FWD_STATE, {})
    st.setdefault("cursor_seq", 0)
    st.setdefault("seen", [])
    st.setdefault("attempts", {})
    st.setdefault("quarantined", {})
    st.setdefault("last_relay_ts", None)
    st.setdefault("last_key", None)
    st.setdefault("corrupt_skipped", 0)
    st.setdefault("invalid_sig_skipped", 0)
    st.setdefault("dup_suppressed", 0)
    return st


def save_state(st):
    # seen as ordered list (cap); attempts/quarantine kept small by design.
    # Transient _-prefixed keys (e.g. _seen_set) are stripped: not JSON-safe.
    st["seen"] = st["seen"][-SEEN_CAP:]
    clean = {k: v for k, v in st.items() if not k.startswith("_")}
    C.atomic_write_json(C.FWD_STATE, clean)


def mark_seen(st, key):
    if key not in st["_seen_set"]:
        st["_seen_set"].add(key)
        st["seen"].append(key)


def reconcile_channel_keys():
    """Keys already posted to the dest channel (crash-recovery idempotency)."""
    keys = set()
    d = C.CHAT_ROOT / C.DEST_CHANNEL
    if not d.is_dir():
        return keys
    try:
        p = subprocess.run(
            ["rg", "--no-filename", "--no-line-number", "^relay_key: ", str(d)],
            capture_output=True, text=True, timeout=60)
        if p.returncode == 0:
            for line in p.stdout.splitlines():
                m = RELAY_KEY_RE.match(line.strip())
                if m:
                    keys.add(m.group(1))
            C.log("reconciled %d relay_key values from #%s (rg)" % (len(keys), C.DEST_CHANNEL))
            return keys
    except (OSError, subprocess.SubprocessError):
        pass
    # fallback: pure-python scan
    for f in d.glob("*.md"):
        try:
            for line in f.read_text(errors="replace").splitlines():
                if line.startswith("relay_key:"):
                    keys.add(line.split(":", 1)[1].strip())
                    break
        except OSError:
            continue
    C.log("reconciled %d relay_key values from #%s (scan)" % (len(keys), C.DEST_CHANNEL))
    return keys


def _chat_stack():
    """Import the squawk signed-post stack (same code the CLI uses)."""
    sys.path.insert(0, str(C.SQUAWK_CODE))
    import fleet_relay
    import chat_commands
    fleet_relay.ensure_keys_env(root=C.CHAT_ROOT)
    key_dir = fleet_relay.resolve_key_dir(None, root=C.CHAT_ROOT)
    return chat_commands, key_dir


def post_entry(chat_commands, key_dir, entry, key):
    channel = entry.get("channel", "?")
    author = entry.get("author", "unknown")
    text = entry.get("text", "")
    body = "[relayed #%s by @%s]\n\n%s" % (channel, author, text)
    title = entry.get("title") or ("relayed from #%s" % channel)
    seq, fname = chat_commands._post_message(
        C.CHAT_ROOT, C.DEST_CHANNEL,
        body=body,
        sender=C.RELAY_IDENTITY,
        to=entry.get("to") or "all",
        status="discussion",
        title=title,
        extra_frontmatter={
            "relayed_from": "squawk:" + channel,
            "human": author,
            "relay_key": key,
        },
        key_dir=key_dir,
    )
    return seq, fname


def record_hop(st, entry, key):
    """HFT-style per-hop latency sample: msg->outbox and outbox->post.

    Kept as a capped ring (200) in forward-state.json; relay-status
    summarizes p50/p95/max per hop. If you can't see it, you can't cut it.
    """
    now = time.time()
    t_msg = C.parse_ts(entry.get("ts", ""))
    t_ing = C.parse_ts(entry.get("ingest_ts", ""))
    sample = {
        "seq": entry.get("seq"),
        "key": key,
        "wall": C.now_iso(),
        "t_msg_to_outbox_s": round(t_ing - t_msg, 3) if t_msg and t_ing else None,
        "t_outbox_to_post_s": round(now - t_ing, 3) if t_ing else None,
    }
    st.setdefault("hop_samples", []).append(sample)
    st["hop_samples"] = st["hop_samples"][-200:]


def read_outbox():
    entries = []
    try:
        data = C.OUTBOX.read_text()
    except OSError:
        return entries, 0
    corrupt = 0
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            corrupt += 1
    return entries, corrupt


def forward_once(st, chat_commands, key_dir):
    entries, corrupt = read_outbox()
    if corrupt and corrupt != st.get("_last_corrupt", 0):
        C.log("WARNING: %d corrupt outbox line(s) skipped (fail loud, queue continues)" % corrupt)
        st["corrupt_skipped"] = st.get("corrupt_skipped", 0) + (corrupt - st.get("_last_corrupt", 0))
        st["_last_corrupt"] = corrupt
    pending = sorted(
        (e for e in entries if isinstance(e, dict) and int(e.get("seq", 0)) > st["cursor_seq"]),
        key=lambda e: int(e.get("seq", 0)))
    if not pending:
        return 0
    done = 0
    for e in pending:
        seq = int(e.get("seq", 0))
        key = C.derive_key(e)
        if key in st["_seen_set"]:
            st["dup_suppressed"] += 1
            C.log("dup suppressed key=%s seq=%d" % (key, seq))
            st["cursor_seq"] = max(st["cursor_seq"], seq)
            save_state(st)
            done += 1
            continue
        if key in st["quarantined"]:
            C.log("quarantined key=%s seq=%d (%s)" % (key, seq, st["quarantined"][key]))
            st["cursor_seq"] = max(st["cursor_seq"], seq)
            save_state(st)
            continue
        if e.get("sig", "valid") != "valid":
            st["invalid_sig_skipped"] += 1
            C.log("invalid signature, not relaying key=%s seq=%d sig=%s" % (key, seq, e.get("sig")))
            mark_seen(st, key)
            st["cursor_seq"] = max(st["cursor_seq"], seq)
            save_state(st)
            continue
        try:
            fseq, fname = post_entry(chat_commands, key_dir, e, key)
        except Exception as ex:
            n = st["attempts"].get(key, 0) + 1
            st["attempts"][key] = n
            save_state(st)
            if n >= MAX_ATTEMPTS:
                st["quarantined"][key] = "post failed %dx: %r" % (n, ex)
                st["attempts"].pop(key, None)
                st["cursor_seq"] = max(st["cursor_seq"], seq)
                save_state(st)
                C.log("QUARANTINED key=%s seq=%d after %d attempts: %r" % (key, seq, n, ex))
                continue
            C.log("post failed (attempt %d/%d) key=%s seq=%d: %r -- blocking queue, will retry"
                  % (n, MAX_ATTEMPTS, key, seq, ex))
            return done  # do not advance: retry next sweep, order preserved
        mark_seen(st, key)
        st["attempts"].pop(key, None)
        st["cursor_seq"] = max(st["cursor_seq"], seq)
        st["last_relay_ts"] = C.now_iso()
        st["last_key"] = key
        record_hop(st, e, key)
        save_state(st)  # atomic commit AFTER post: at-least-once
        done += 1
        C.log("relayed seq=%d -> #%s/%s key=%s" % (seq, C.DEST_CHANNEL, fname, key))
    return done


def main():
    C.acquire_lock("forward")
    st = load_state()
    st["_seen_set"] = set(st["seen"])
    st["_last_corrupt"] = 0
    # crash-recovery idempotency: never double-post across restarts
    for k in reconcile_channel_keys():
        if k not in st["_seen_set"]:
            st["_seen_set"].add(k)
            st["seen"].append(k)
    save_state(st)
    chat_commands, key_dir = _chat_stack()
    C.log("forwarder starting: outbox=%s dest=#%s cursor=%d seen=%d" % (
        C.OUTBOX, C.DEST_CHANNEL, st["cursor_seq"], len(st["_seen_set"])))
    try:
        ino = C.Inotify([C.RELAY_DIR])
    except OSError as e:
        C.log("inotify unavailable (%s); poll fallback" % e)
        ino = None
    last = 0.0
    while True:
        try:
            if ino and ino.wait(5.0):
                time.sleep(DEBOUNCE)
                forward_once(st, chat_commands, key_dir)
                last = time.monotonic()
            elif time.monotonic() - last >= SWEEP_INTERVAL:
                forward_once(st, chat_commands, key_dir)
                last = time.monotonic()
        except Exception as e:
            C.log("forward error (retrying): %r" % e)
            time.sleep(5.0)


if __name__ == "__main__":
    main()
