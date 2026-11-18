#!/usr/bin/env python3
"""Seed genuine labels into the calibration history from bench evals.

The abstention gate and the calibrator consume ONLY rows with an
explicit label_source (see calibration.labeled_history / engine._accepted
_history). Labeled bench evals are the honest bootstrap source: their
rows come from real verdicts graded against known labels, entered
through the validated entry point engine.record_accepted_outcome.

Usage:
  python3 bench/seed_bench_labels.py bench/results/eval_<ts>.jsonl [--apply]

Default is a dry run (prints what would be written). --apply writes.
Idempotent: eval_ids already present in the history are skipped.

What counts: rows with status "verdict" and label in (0,1). Escalated
rows are excluded (no probability was emitted, so there is no panel
answer to grade).
"""
import argparse
import json
import os
import sys

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BIN, "..", "bin"))

import engine
import calibration as cal


def _existing_ids():
    ids = set()
    rows, _ = cal.labeled_history()
    for r in rows:
        q = r.get("question_id")
        if q:
            ids.add(q)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="labeled eval results jsonl")
    ap.add_argument("--apply", action="store_true",
                    help="actually write (default: dry run)")
    ap.add_argument("--source", default="bench")
    args = ap.parse_args()

    if args.source not in engine.LABEL_SOURCES:
        print("refusing: source %r not in LABEL_SOURCES" % args.source,
              file=sys.stderr)
        return 2

    existing = _existing_ids()
    candidates = []
    skipped = 0
    with open(args.results) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("status") != "verdict":
                continue
            if r.get("label") not in (0, 1):
                continue
            p = r.get("probability")
            if not isinstance(p, (int, float)):
                continue
            eid = r.get("eval_id") or r.get("question_id") or r.get("question", "")[:40]
            if eid in existing:
                skipped += 1
                continue
            correct = (p >= 0.5) == bool(r["label"])
            candidates.append({"question_id": eid, "correct": bool(correct),
                               "probability": float(p),
                               "label": int(r["label"])})

    print("candidates: %d  already-seeded (skipped): %d  apply: %s"
          % (len(candidates), skipped, args.apply))
    if not args.apply:
        for c in candidates[:10]:
            print("  would seed %s correct=%s" % (c["question_id"], c["correct"]))
        if len(candidates) > 10:
            print("  ... and %d more" % (len(candidates) - 10))
        return 0

    n = 0
    for c in candidates:
        engine.record_accepted_outcome(
            c["question_id"], c["correct"], source=args.source,
            note="bench eval seed: %s p=%.3f label=%d"
            % (os.path.basename(args.results), c["probability"], c["label"]))
        n += 1
    rows, quarantined = cal.labeled_history()
    print("seeded %d rows; history now: %d genuine, %d quarantined"
          % (n, len(rows), quarantined))
    return 0


if __name__ == "__main__":
    sys.exit(main())
