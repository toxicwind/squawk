#!/usr/bin/env python3
"""Coverage-risk curve for the oracle abstention operating point.

Safety vs served-traffic tradeoff (2609.22048: exact-binomial inversion
makes finite-sample safety certificates computable; plan/select split
keeps the selection honest):

  * planning split: candidate operating points = margin rules
    "emit iff |posterior-0.5| >= m" for m in the grid. Plan-side coverage
    measured here.
  * selection split: each candidate's empirical risk and a Clopper-Pearson
    lower bound on accuracy measured here. The production safety bar
    (engine.GATE_MIN_ACCURACY) is checked against the SELECTION split,
    never the planning split (no data snooping).

Input: labeled eval results jsonl (bench/grade_eval.py schema: rows with
  "label" in (0,1), "probability", "status").
Output: JSON curve {operating_points: [{margin, coverage_plan,
  coverage_select, risk_select, n_select, accuracy_lo, meets_safety}], ...}
plus the production history-based operating point for reference.

Note the two operating points are different instruments: the production
gate (engine.abstention_gate) is a GLOBAL history gate over genuine
labels; this curve is a PER-QUESTION selective rule. Both expose the
same tradeoff: higher safety <=> less served traffic.
"""
import argparse
import json
import os
import sys

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BIN, "..", "bin"))

_oracle_work = os.environ.get("ORACLE_WORK")
if _oracle_work:
    os.environ["ORACLE_WORK"] = _oracle_work

import engine
import calibration as cal


def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if (r.get("status") == "verdict"
                    and r.get("label") in (0, 1)
                    and isinstance(r.get("probability"), (int, float))):
                rows.append({"p": float(r["probability"]),
                             "label": int(r["label"])})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="labeled eval results jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--margins", default="0.0,0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45")
    args = ap.parse_args()

    rows = load_rows(args.results)
    if len(rows) < 4:
        print("not enough labeled verdict rows: %d" % len(rows),
              file=sys.stderr)
        return 2
    # deterministic plan/select split (interleaved, no RNG)
    plan = rows[::2]
    select = rows[1::2]
    margins = [float(x) for x in args.margins.split(",")]

    points = []
    for m in margins:
        served_p = [r for r in plan if abs(r["p"] - 0.5) >= m]
        served_s = [r for r in select if abs(r["p"] - 0.5) >= m]
        cov_p = len(served_p) / max(1, len(plan))
        cov_s = len(served_s) / max(1, len(select))
        n = len(served_s)
        if n:
            errs = sum(1 for r in served_s
                       if (r["p"] >= 0.5) != bool(r["label"]))
            risk = errs / n
            acc_lo, _ = cal.clopper_pearson(n - errs, n)
        else:
            risk = None
            acc_lo = None
        points.append({
            "margin": m,
            "coverage_plan": round(cov_p, 4),
            "coverage_select": round(cov_s, 4),
            "risk_select": round(risk, 4) if risk is not None else None,
            "n_select": n,
            "accuracy_lo_select": round(acc_lo, 4)
            if acc_lo is not None else None,
            "meets_safety_select": (acc_lo is not None
                                    and acc_lo >= engine.GATE_MIN_ACCURACY),
        })

    out = {
        "results": args.results,
        "n_rows": len(rows),
        "n_plan": len(plan),
        "n_select": len(select),
        "safety_target": engine.GATE_MIN_ACCURACY,
        "production_operating_point": engine.gate_operating_point(),
        "operating_points": points,
    }
    text = json.dumps(out, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
        print("wrote %s (%d rows, %d/%d plan/select)"
              % (args.out, len(rows), len(plan), len(select)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
