#!/usr/bin/env python3
"""Experiment: calibration reduces held-out NLL on synthetic miscalibrated judges.

Setup: 3 synthetic judges with KNOWN miscalibration shapes —
  j1 overconfident (pushes to extremes), j2 underconfident (shrinks to 0.5),
  j3 systematically high by +0.1.
Ground truth: p_true ~ U(0.05, 0.95); labels ~ Bernoulli(p_true).
Each judge reports a distorted p_true; we cross-fit Platt + isotonic on
train labels, then compare raw vs calibrated NLL on held-out labels.

Claim under test: the better of (Platt, isotonic) — chosen by the
CalibrationLoop's own precision gate — beats raw NLL on held-out data.
Deterministic (seeded RNG). No model calls.
"""
import os
import random
import sys

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
sys.path.insert(0, BIN)
os.environ.setdefault("ORACLE_WORK", "/tmp/oracle-exp-work")

import calibration as cal

random.seed(20260920)


def distort(kind, p):
    if kind == "over":
        return min(0.99, max(0.01, p + 0.25 * (p - 0.5) * 2))
    if kind == "under":
        return 0.5 + (p - 0.5) * 0.5
    if kind == "bias":
        return min(0.99, max(0.01, p + 0.10))
    raise ValueError(kind)


def run(n_train=400, n_test=400):
    kinds = {"j1": "over", "j2": "under", "j3": "bias"}
    results = {}
    for jid, kind in kinds.items():
        p_true = [random.uniform(0.05, 0.95) for _ in range(n_train + n_test)]
        rep = [distort(kind, p) for p in p_true]
        lab = [1 if random.random() < p else 0 for p in p_true]
        tr_s, te_s = rep[:n_train], rep[n_train:]
        tr_l, te_l = lab[:n_train], lab[n_train:]
        raw_nll = cal.nll(te_s, te_l)
        platt_cf = cal.cross_fitted_predict(cal.platt_fit, cal.platt_predict,
                                            tr_s, tr_l)
        iso_cf = cal.cross_fitted_predict(cal.isotonic_fit,
                                          cal.isotonic_predict, tr_s, tr_l)
        pl_nll, iso_nll = cal.nll(platt_cf, tr_l), cal.nll(iso_cf, tr_l)
        # deploy per the loop's own precision gate, then score on held-out
        use_platt = pl_nll <= iso_nll
        if min(pl_nll, iso_nll) >= cal.nll(tr_s, tr_l):
            cal_nll = raw_nll  # gate refuses: no calibration deployed
            kind_used = "none(refused)"
        else:
            model = (cal.platt_fit(tr_s, tr_l) if use_platt
                     else cal.isotonic_fit(tr_s, tr_l))
            pred = (cal.platt_predict if use_platt else cal.isotonic_predict)
            cal_nll = cal.nll([pred(model, [s])[0] for s in te_s], te_l)
            kind_used = "platt" if use_platt else "isotonic"
        results[jid] = {"miscalibration": kind, "deployed": kind_used,
                        "raw_nll": round(raw_nll, 4),
                        "calibrated_nll": round(cal_nll, 4),
                        "improvement": round(raw_nll - cal_nll, 4)}
    return results


def main():
    res = run()
    ok = True
    for jid, r in res.items():
        status = "OK " if r["improvement"] >= -1e-9 else "REGRESSED"
        if r["improvement"] < -1e-9:
            ok = False
        print("%s %-4s %-5s raw=%.4f cal=%.4f Δ=%.4f (%s)" %
              (status, jid, r["miscalibration"], r["raw_nll"],
               r["calibrated_nll"], r["improvement"], r["deployed"]))
    print("RESULT:", "PASS — calibration never regresses held-out NLL"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
