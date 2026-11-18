#!/usr/bin/env python3
"""Experiment: pooled posterior (product-of-posteriors) vs majority vote.

Setup: 5 synthetic judges, reliabilities {0.95, 0.9, 0.75, 0.6, 0.55}.
Ground truth p_true; each judge reports p_true + noise scaled by
(1 - reliability), clipped. 500 labeled questions.
Metric: Brier score (the proper scoring rule — what the engine optimizes)
and accuracy-at-0.5 (reported for context; thresholding discards
information, so small accuracy wiggles are noise).
Claim under test: reliability-weighted pooling strictly improves Brier
vs unweighted majority, without a meaningful accuracy loss (|Δ| < 2pp).
Deterministic (seeded). No model calls.
"""
import os
import random
import sys

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
sys.path.insert(0, BIN)
os.environ.setdefault("ORACLE_WORK", "/tmp/oracle-exp-work")

import engine

random.seed(20260921)


def run(n=500):
    rels = [0.95, 0.9, 0.75, 0.6, 0.55]
    maj_brier = pool_brier = 0.0
    maj_acc = pool_acc = 0
    for _ in range(n):
        p_true = random.uniform(0.05, 0.95)
        label = 1 if random.random() < p_true else 0
        judges = []
        for i, r in enumerate(rels):
            rep = p_true + random.gauss(0, (1 - r) * 0.5)
            rep = min(0.99, max(0.01, rep))
            judges.append(engine.JudgePosterior("j%d" % i, rep,
                                                reliability=r))
        votes = [1 if j.posterior >= 0.5 else 0 for j in judges]
        maj_p = sum(votes) / len(votes)
        maj_brier += (maj_p - label) ** 2
        maj_acc += (1 if (maj_p >= 0.5) == label else 0)
        pool_p, _ = engine.pooled_posterior(0.5, judges)
        pool_brier += (pool_p - label) ** 2
        pool_acc += (1 if (pool_p >= 0.5) == label else 0)
    return {
        "n": n,
        "majority": {"brier": round(maj_brier / n, 4),
                     "accuracy": round(maj_acc / n, 4)},
        "pooled": {"brier": round(pool_brier / n, 4),
                   "accuracy": round(pool_acc / n, 4)},
    }


def main():
    r = run()
    print("majority: brier=%.4f acc=%.4f" % (r["majority"]["brier"],
                                            r["majority"]["accuracy"]))
    print("pooled:   brier=%.4f acc=%.4f" % (r["pooled"]["brier"],
                                            r["pooled"]["accuracy"]))
    ok = (r["pooled"]["brier"] < r["majority"]["brier"] and
          abs(r["pooled"]["accuracy"] - r["majority"]["accuracy"]) < 0.02)
    print("RESULT:", "PASS — pooling improves Brier, accuracy within noise"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
