#!/usr/bin/env python3
"""Post a control-plane task_post to the bid-market channel.

Control-plane messages are HMAC-authenticated under the oracle-held
control key (SPEC §1.5) — the `from:` frontmatter field is spoofable and
is never trusted. The oracle creates the control key on first start
(/home/toxic/.openfang/stake-registry/control.key, mode 600); this tool
reads it and fails loudly if it is absent.

Usage:
  post_task.py --id tau-1826-health --title "tau-1826-health" \\
      --tags code-fix,probe --timeout-ms 300000 --bid-window-ms 15000 \\
      --payload-file /tmp/pol-task1.py
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

BIN = Path("/home/toxic/estate/ranch/squawk/oracle/bin")
sys.path.insert(0, str(BIN))

_spec = importlib.util.spec_from_file_location("bidder", BIN / "bidder.py")
bidder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bidder)
import sealed as sealed_mod  # noqa: E402  (after sys.path.insert for sibling-dir import)
import mechanism as mech  # noqa: E402  (after sys.path.insert for sibling-dir import)


def load_control_hmac_key() -> bytes:
    """Read the oracle's control master and derive the HMAC key.
    Never creates it: only the oracle loop may mint the control key."""
    p = mech.control_key_path()
    if not p.exists():
        sys.stderr.write(
            f"post_task: control key {p} missing — start the oracle loop "
            "once so it mints the key, then re-run.\n")
        sys.exit(2)
    master = p.read_text(encoding="utf-8").strip()
    return sealed_mod.hkdf(bytes.fromhex(master), sealed_mod.CTL_INFO)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--tags", required=True)
    ap.add_argument("--timeout-ms", type=int, default=300000)
    ap.add_argument("--bid-window-ms", type=int, default=15000)
    ap.add_argument("--payload-file", required=True)
    ap.add_argument("--from", dest="frm", default="ember")
    ap.add_argument("--exec-mode", default="python",
                    help="execution mode: python (default) or super-ralph")
    args = ap.parse_args()

    ctl_hmac = load_control_hmac_key()
    payload = Path(args.payload_file).read_text(encoding="utf-8")
    poster = bidder.SeqPoster(bidder.CHANNEL, "bid-market", args.frm)
    body = {
        "task_id": args.id,
        "title": args.title,
        "payload": payload,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
        "bid_window_ms": args.bid_window_ms,
        "timeout_ms": args.timeout_ms,
        "exec_mode": args.exec_mode,
        "posted_ts": time.time(),
    }
    ctl_ts = int(time.time())
    ctl_sig = sealed_mod.sign_control(
        ctl_hmac, "task_post", args.id,
        sealed_mod.ctl_body_sha256(body), ctl_ts)
    # raw_body with canonical JSON: the oracle recomputes the body digest
    # from the parsed dict, so any parse-stable serialization works, but
    # canonical form keeps the channel human-diffable.
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    name = poster.post("task_post", f"task-{args.id}", canon, task_id=args.id,
                       raw_body=True,
                       extra_fm={"ctl_sig": ctl_sig, "ctl_ts": ctl_ts},
                       note=f"task posted: {args.title} "
                            f"[tags: {args.tags}] timeout {args.timeout_ms}ms "
                            f"(control-signed).")
    print(f"posted {name}")


if __name__ == "__main__":
    main()
