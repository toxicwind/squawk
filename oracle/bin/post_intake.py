#!/usr/bin/env python3
"""Post an intake_request to the bid-market channel (oracle front door).

intake_request is NOT a control-plane message: anyone may post one. The
oracle triages it (bin/oracle_intake.py) behind ORACLE_INTAKE=1 and opens
an auction only for TASK-route decisions; the triage decision is recorded
append-only in the market ledger.

Usage:
  post_intake.py --from ember-intake-test \
      --text "fix the broken health probe"
"""
import argparse
import importlib.util
import sys
import time
from pathlib import Path

BIN = Path("/home/toxic/estate/ranch/squawk/oracle/bin")
sys.path.insert(0, str(BIN))

_spec = importlib.util.spec_from_file_location("bidder", BIN / "bidder.py")
bidder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bidder)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="ember")
    ap.add_argument("--text", required=True)
    args = ap.parse_args()
    poster = bidder.SeqPoster(bidder.CHANNEL, "bid-market", args.frm)
    body = {"text": args.text, "posted_ts": time.time()}
    name = poster.post("intake_request", "intake-%d" % int(time.time()),
                       body, note="intake request from %s" % args.frm)
    print("posted %s" % name)


if __name__ == "__main__":
    main()
