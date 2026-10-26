#!/usr/bin/env python3
"""Seed genuine labels into the calibration history from market settles.

The abstention gate and the calibrator consume ONLY rows with an
explicit label_source (see calibration.labeled_history / engine._accepted
_history). Market settles that the oracle market itself marked
verified=true AND success=true are the honest market source: the bidder's
work product was independently verified, and the accept decision
resolved as a genuine outcome.

What counts (strict):
  * event == "settled"
  * verified is True AND success is True
  * replay is not True (replays are not independent outcomes)
  * dedupe by task_id (ledger may carry duplicate settle lines)

Everything else is EXCLUDED and reported by category:
  * verified=False (no-result / exec-timeout / failed-verification) --
    these carry NO ground truth about the accepted outcome
  * slashed / bond_released_infra / stake_released lines are not settles
    (they are money events, handled by the ledger, not labels)

Semantics caveat (reported in dry-run output): every qualifying row is
correct=True. This is genuine market verification, NOT verdict accuracy:
it certifies that accepted market work verified out, which is the
"market_settlement" source calibration.py blesses -- it is NOT a panel
verdict graded against ground truth. The CP projection printed by
--dry-run shows the resulting (k, n) honestly; combine with bench labels
for a verdict-accuracy-weighted history.

Usage:
  python3 seed_market_labels.py [--ledger PATH] [--apply] [--path OUT]

Default is a dry run (prints what would be written). --apply writes via
engine.record_accepted_outcome (source=market_settlement). Idempotent:
task_ids already present in the history are skipped.

Exit: 0 on success (dry-run or applied), 2 on bad args.
"""
import argparse
import json
import os
import sys

ORACLE = "/home/toxic/estate/ranch/squawk/oracle"
BIN = os.path.join(ORACLE, "bin")
sys.path.insert(0, BIN)

import engine  # noqa: E402
import calibration as cal  # noqa: E402

DEFAULT_LEDGER = os.path.join(ORACLE, "ledger", "ledger.jsonl")


def scan(ledger_path):
    included = []
    excluded = {}
    seen = set()
    with open(ledger_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") != "settled":
                continue
            tid = r.get("task_id") or ""
            if r.get("replay"):
                excluded["replay"] = excluded.get("replay", 0) + 1
                continue
            if r.get("verified") is not True or r.get("success") is not True:
                key = "unverified:%s" % (r.get("reason") or "no-reason")
                excluded[key] = excluded.get(key, 0) + 1
                continue
            if tid in seen:
                excluded["duplicate-task"] = excluded.get("duplicate-task", 0) + 1
                continue
            seen.add(tid)
            included.append({
                "question_id": tid,
                "correct": True,
                "winner": r.get("winner"),
                "ts": r.get("ts"),
                "notes": "; ".join(r.get("notes") or [])[:200],
            })
    return included, excluded


def self_test(rows):
    """Validate our own dry-run rows against calibration's provenance reader.

    Writes rows to a temp path, reads them back through
    cal.labeled_history(source='market_settlement'), and asserts every
    row survives with correct=True. Returns True on pass.
    """
    import tempfile
    tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    try:
        for r in rows:
            tmp.write(json.dumps({
                "question_id": r["question_id"],
                "correct": r["correct"],
                "label_source": "market_settlement",
                "note": r["notes"],
            }) + "\n")
        tmp.close()
        back, quarantined = cal.labeled_history(
            source="market_settlement", path=tmp.name)
        ok = (len(back) == len(rows) and quarantined == 0
              and all(b["correct"] for b in back))
        return ok
    finally:
        os.unlink(tmp.name)


def cp_projection(k, n, alpha=engine.GATE_ALPHA):
    lo, hi = cal.clopper_pearson(k, n, alpha)
    return {"k": k, "n": n, "cp_lo": lo, "cp_hi": hi,
            "gate_target": engine.GATE_MIN_ACCURACY,
            "would_emit": bool(lo >= engine.GATE_MIN_ACCURACY)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--apply", action="store_true",
                    help="actually write (default: dry run)")
    args = ap.parse_args()

    if not os.path.exists(args.ledger):
        print("refusing: ledger not found: %s" % args.ledger,
              file=sys.stderr)
        return 2

    included, excluded = scan(args.ledger)
    existing = {r.get("question_id") for r in cal.labeled_history()[0]}
    new = [r for r in included if r["question_id"] not in existing]
    skipped = len(included) - len(new)

    print("settled verified+success: %d  already-seeded (skipped): %d  "
          "to-write: %d  apply: %s" % (len(included), skipped, len(new),
                                       args.apply))
    if excluded:
        print("excluded:")
        for k, v in sorted(excluded.items(), key=lambda x: -x[1]):
            print("  %s: %d" % (k, v))

    ok = self_test(new)
    print("self-test (schema vs calibration reader): %s" % ("PASS" if ok else "FAIL"))
    if not ok:
        return 2

    rows, _ = cal.labeled_history()
    k_all, n_hist = sum(1 for r in rows if r["correct"]), len(rows)
    proj = cp_projection(k_all + len(new), n_hist + len(new))
    print("gate projection with new rows (k=%d, n=%d): CP lo=%.4f hi=%.4f "
          "target=%.2f -> %s" % (
              proj["k"], proj["n"], proj["cp_lo"], proj["cp_hi"],
              proj["gate_target"],
              "EMIT" if proj["would_emit"] else "ESCALATE"))
    print("NOTE: all %d rows are correct=True (market verification, not "
          "verdict accuracy)" % len(new))

    if not args.apply:
        for r in new[:10]:
            print("  would seed %s winner=%s" % (r["question_id"], r["winner"]))
        if len(new) > 10:
            print("  ... and %d more" % (len(new) - 10))
        return 0

    n = 0
    for r in new:
        engine.record_accepted_outcome(
            r["question_id"], True, source="market_settlement",
            note="market settle verified: winner=%s; %s"
                 % (r["winner"], r["notes"]))
        n += 1
    rows2, q2 = cal.labeled_history()
    print("seeded %d rows; history now: %d genuine, %d quarantined"
          % (n, len(rows2), q2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
