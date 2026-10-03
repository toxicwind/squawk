#!/usr/bin/env python3
"""E2E proof for squawk-relay: inject -> outbox -> fleet, then re-inject same
key -> prove no duplicate. Prints PASS/FAIL with evidence.

Usage: python3 e2e-test.py
"""
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/home/toxic/.fleet-bus/squawk-relay")
import relay_common as C

TOKEN = "e2e-" + uuid.uuid4().hex[:8]
SRC_CHANNEL = "leads"
PROBE_AUTHOR = "shingle"  # has a signing key; not in sink skip_authors
TIMEOUT = 90


def log(msg):
    print("[e2e] %s" % msg, flush=True)


def chat_stack():
    sys.path.insert(0, str(C.SQUAWK_CODE))
    import fleet_relay
    import chat_commands
    fleet_relay.ensure_keys_env(root=C.CHAT_ROOT)
    key_dir = fleet_relay.resolve_key_dir(None, root=C.CHAT_ROOT)
    return chat_commands, key_dir


def wait_for(desc, fn, timeout=TIMEOUT):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(1.0)
    raise AssertionError("TIMEOUT waiting for: %s" % desc)


def main():
    results = {}
    chat_commands, key_dir = chat_stack()

    # ---- 1. inject at source (signed path) ----
    body = "E2E relay probe %s -- unique token, please ignore" % TOKEN
    src_seq, src_file = chat_commands._post_message(
        C.CHAT_ROOT, SRC_CHANNEL, body=body, sender=PROBE_AUTHOR,
        to="all", status="discussion", title="e2e probe %s" % TOKEN,
        key_dir=key_dir)
    log("injected #%s msg seq=%d file=%s" % (SRC_CHANNEL, src_seq, src_file))
    results["src_seq"] = src_seq

    # ---- 2. sink ingests -> outbox record with global seq + key ----
    def find_outbox():
        for line in C.OUTBOX.read_text().splitlines():
            line = line.strip()
            if line and TOKEN in line:
                return json.loads(line)
        return None

    rec = wait_for("outbox record", find_outbox, 30)
    key = rec["idempotency_key"]
    oseq = rec["seq"]
    assert rec["sig"] == "valid", "probe sig not valid: %s" % rec.get("sig")
    assert oseq > 7, "unexpected outbox seq"
    log("outbox: seq=%d key=%s sig=valid" % (oseq, key))
    results.update(outbox_seq=oseq, key=key)

    # ---- 3. forwarder posts -> same relay_key in #fleet ----
    rk_re = re.compile(r"^relay_key:\s*(\S+)\s*$", re.M)

    def find_fleet():
        d = C.CHAT_ROOT / C.DEST_CHANNEL
        for f in sorted(d.glob("*.md")):
            m = rk_re.search(f.read_text())
            if m and m.group(1) == key:
                return f.name
        return None

    fname = wait_for("fleet relay_key", find_fleet)
    log("fleet: %s carries relay_key=%s" % (fname, key))
    results["fleet_file"] = fname

    # ---- 4. re-inject SAME key as a new outbox record (at-least-once dup) ----
    max_seq = max(int(json.loads(l)["seq"]) for l in C.OUTBOX.read_text().splitlines() if l.strip())
    dup = dict(rec)
    dup["seq"] = max_seq + 1
    dup["ingest_ts"] = C.now_iso()
    dup["note"] = "e2e duplicate re-injection (same idempotency key)"
    with open(C.OUTBOX, "a") as fh:
        fh.write(json.dumps(dup) + "\n")
        fh.flush()
        try:
            import os
            os.fsync(fh.fileno())
        except OSError:
            pass
    log("re-injected same key as outbox seq=%d" % dup["seq"])
    results["dup_seq"] = dup["seq"]

    # ---- 5. forwarder must suppress the duplicate ----
    def dup_seen():
        st = json.loads(C.FWD_STATE.read_text())
        return st.get("dup_suppressed", 0) if st.get("dup_suppressed", 0) > results.get("dup0", 0) else None

    st0 = json.loads(C.FWD_STATE.read_text())
    results["dup0"] = st0.get("dup_suppressed", 0)

    def dup_incr():
        st = json.loads(C.FWD_STATE.read_text())
        return st.get("dup_suppressed", 0) > results["dup0"] or None

    wait_for("dup_suppressed increment", dup_incr)
    log("dup_suppressed incremented: %d -> %d" % (
        results["dup0"], json.loads(C.FWD_STATE.read_text()).get("dup_suppressed", 0)))

    # ---- 6. exactly one fleet message carries the key ----
    time.sleep(2)  # let any erroneous second post land
    d = C.CHAT_ROOT / C.DEST_CHANNEL
    hits = [f.name for f in d.glob("*.md")
            if (m := rk_re.search(f.read_text())) and m.group(1) == key]
    assert len(hits) == 1, "DUPLICATE POSTED: %s" % hits
    log("fleet has exactly 1 message with key %s" % key)

    # ---- 7. hop telemetry ----
    st = json.loads(C.FWD_STATE.read_text())
    for s in st.get("hop_samples", [])[-3:]:
        if s.get("key") == key:
            log("hop sample: msg->outbox=%.3fs outbox->post=%.3fs" % (
                s.get("t_msg_to_outbox_s") or -1, s.get("t_outbox_to_post_s") or -1))
            results["hop"] = {k: s.get(k) for k in ("t_msg_to_outbox_s", "t_outbox_to_post_s")}

    print("\nE2E RESULT: PASS")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        print("\nE2E RESULT: FAIL: %s" % ex)
        sys.exit(1)
