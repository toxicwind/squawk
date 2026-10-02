#!/usr/bin/env python3
"""EXP-ABSTAIN — abstention gate experiment, 2026-09-21 (redesign).

The gate is a FINITE-SAMPLE safety instrument, not a hand-tuned bar:

  1. Cold start: with zero genuine labels the gate WITHHOLDS even at
     posterior 0.99 / confidence 0.99. The old cold-unanimity bypass is
     gone; the reason cites n=0 and the finite-sample bound.
  2. Finite-sample honesty: 38/40 labeled emits; 19/20 and 14/20 withhold.
     The old hand-tuned `struct_bar`/`post_bar` parameters are gone —
     the only knob is GATE_MIN_ACCURACY plus the Clopper-Pearson bound.
  3. Monotonicity: once the gate emits, additional correct labels never
     flip it back to escalate.
  4. Provenance: legacy history rows without an explicit label_source are
     QUARANTINED (counted, never evidence). 40 genuine + 100 legacy rows
     still emit on the 40 genuine alone.
  5. Shrinkage + honesty: shrunk_accuracy(0,0) == 0.5 (prior reported, not
     hidden); the gate and operating_point() never write to the history.
  6. Provenance enforcement: record_accepted_outcome requires a valid
     source; the gate bootstrap entry point is bench/seed_bench_labels.py
     (bench evals graded against known labels).

The safety-vs-served-traffic frontier is swept by bench/coverage_risk.py
(plan/select split, per-question margin rule). This experiment validates
the GLOBAL history gate; coverage_risk.py draws the curve.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "bin"))
import engine
import calibration as cal


def fresh():
    cal.CAL_DIR = tempfile.mkdtemp(prefix="exp-abstain-")
    cal.HISTORY_PATH = os.path.join(cal.CAL_DIR, "accepted_history.jsonl")
    cal.DATASHEET_PATH = os.path.join(cal.CAL_DIR, "judge_datasheets.json")
    cal.CAL_STATE_PATH = os.path.join(cal.CAL_DIR, "calibration_state.json")


def gate(post=0.9, conf=0.8):
    """-> (decision, reason, operating_point)."""
    decision, reason = engine.abstention_gate(post, conf)
    return decision, reason, engine.gate_operating_point()


def main():
    results = []

    def check(name, cond, detail=""):
        results.append((name, cond, detail))
        print(("ok   " if cond else "FAIL ") + name +
              ("" if cond else " " + str(detail)))

    # 1. cold start withholds even at 0.99/0.99 (no unanimity bypass)
    fresh()
    g, reason, op = gate(0.99, 0.99)
    check("1. cold 0.99/0.99 withholds", g == "escalate", (g, reason))
    check("1. reason cites n=0", "n=0" in reason or "0 labeled" in reason,
          reason)
    check("1. no unanimity bypass",
          op["history_n"] == 0 and g != "verdict", op)
    check("1. no history file created",
          not os.path.exists(cal.HISTORY_PATH))

    # 2. finite-sample honesty
    fresh()
    for i in range(40):
        engine.record_accepted_outcome("q%d" % i, i < 38, source="bench")
    g, reason, op = gate()
    check("2. 38/40 emits", g == "emit", (g, reason))
    check("2. served_planned true", op["served_planned"] is True, op)

    fresh()
    for i in range(20):
        engine.record_accepted_outcome("q%d" % i, i < 19, source="bench")
    g, reason, op = gate()
    check("2. 19/20 withholds", g == "escalate", (g, reason))

    fresh()
    for i in range(20):
        engine.record_accepted_outcome("q%d" % i, i < 14, source="bench")
    g, reason, _op = gate()
    check("2. 14/20 withholds", g == "escalate", (g, reason))

    # 3. monotonicity: once emit, more correct labels never flip back
    fresh()
    flips = 0
    ever_emitted = False
    for i in range(60):
        engine.record_accepted_outcome("q%d" % i, True, source="bench")
        g, _, _ = gate()
        if g == "emit":
            ever_emitted = True
        elif ever_emitted:
            flips += 1
    check("3. monotonic: emitted then stayed emitted",
          ever_emitted and flips == 0, (ever_emitted, flips))

    # 4. provenance: legacy rows quarantined
    fresh()
    for i in range(40):
        engine.record_accepted_outcome("q%d" % i, i < 38, source="bench")
    with open(cal.HISTORY_PATH, "a") as f:
        for i in range(100):
            f.write(json.dumps({"question_id": "legacy%d" % i,
                                "correct": True}) + "\n")
    g, reason, op = gate()
    check("4. 40 genuine + 100 legacy emits on genuine alone",
          g == "emit" and op["history_n"] == 40, (g, op))
    check("4. legacy quarantined", op["quarantined_rows"] == 100, op)

    # 5. shrinkage + no synthetic writes
    check("5. shrunk(0,0)==0.5 (prior reported, not hidden)",
          engine.shrunk_accuracy(0, 0) == 0.5)
    fresh()
    for i in range(3):
        engine.record_accepted_outcome("q%d" % i, i < 2, source="bench")
    before = open(cal.HISTORY_PATH).read()
    gate()
    engine.gate_operating_point()
    after = open(cal.HISTORY_PATH).read()
    check("5. gate reads only, never writes synthetic labels",
          before == after)

    # 6. source enforcement
    try:
        engine.record_accepted_outcome("qx", True)
        check("6. source required", False, "no ValueError")
    except ValueError:
        check("6. source required", True)

    fails = [n for n, c, d in results if not c]
    print("---")
    if fails:
        print("FAILURES: %s" % ", ".join(fails))
        return 1
    print("EXP-ABSTAIN: all sections passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
