#!/usr/bin/env python3
"""One-time migration: backfill idempotency keys on legacy outbox entries and
set sink channel cursors to current high-water (relay starts from now).

Safe to re-run: only fills missing keys; cursor set is explicit.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay_common as C

# 1. backfill idempotency keys
lines = [l for l in C.OUTBOX.read_text().splitlines() if l.strip()]
out, filled = [], 0
for line in lines:
    e = json.loads(line)
    if "idempotency_key" not in e:
        e["idempotency_key"] = C.idempotency_key(
            e["channel"], e["msg_seq"], e["author"], e["ts"], e["text"][:500])
        filled += 1
    out.append(e)
C.OUTBOX.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in out) + "\n")
print("backfilled %d/%d entries" % (filled, len(out)))

# 2. sink cursors -> current high-water per channel (start relaying from now)
st = C.load_json(C.SINK_STATE, {"feed_seq": 0, "channels": {}})
for d in C.channel_dirs():
    top = 0
    for f in d.glob("*.md"):
        try:
            top = max(top, int(f.name.split("-", 1)[0]))
        except (ValueError, IndexError):
            continue
    st["channels"][d.name] = top
    print("cursor #%s -> %d" % (d.name, top))
C.atomic_write_json(C.SINK_STATE, st)
print("state.json updated; feed_seq stays", st["feed_seq"])
