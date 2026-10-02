#!/usr/bin/env python3
"""Permanent judge-return harness (free-tier resilience, 2026-09-20).

Measures the live-judge return rate of the Oracle ask path: the fraction
of panel slots that return a usable (non-refused) posterior. Run once
against the OLD implementation (--mode old, concrete model IDs, direct
judge_once) to record the baseline floor, then again against the hardened
implementation (--mode new, router aliases via _resilient_judge) with the
same questions, timeout, and sample size. The return floor and its
Clopper-Pearson lower bound are reported honestly -- no retry loops, no
cherry-picking.

Usage:
  python3 bench/judge_return.py --mode old --bin-dir bin --out \\
      proof-runs/judge_return_baseline.jsonl
  python3 bench/judge_return.py --mode new --bin-dir bin --out \\
      proof-runs/judge_return_hardened.jsonl

Both runs use the same question set, per-slot timeout, and parallelism,
so the floors are directly comparable.
"""
import argparse
import concurrent.futures as cf
import importlib.util
import json
import math
import os
import sys
import time

QUESTIONS = [
    "Will the herd router serve 100 or more models by 2026-12-31?",
    "Will the Oracle market answer five or more live questions by 2026-12-31?",
    "Will CachyOS release a new kernel version by 2026-12-31?",
    "Will the squawk fleet channel carry 20000 or more messages by 2026-12-31?",
    "Will Python 3.14 be released by 2026-12-31?",
]

OLD_MODELS = [
    "openrouter-free/nex-agi/nex-n2.5-mini:free",
    "openrouter-free/nex-agi/nex-n2.5-pro:free",
    "openrouter-free/poolside/laguna-s-2.1:free",
]
NEW_MODELS = ["oracle-judge-a", "oracle-judge-b", "oracle-judge-c"]

PROMPT_T = ("You are a judge on the OpenFang Oracle panel.\n"
            "Question: {q}\n"
            "Reply with JSON ONLY: "
            '{"posterior": <0..1 probability YES>, "reasoning_summary": "<1 line>"}')


def make_prompt(q):
    return PROMPT_T.replace("{q}", q)


def load_oracle_ask(bin_dir):
    bin_dir = os.path.abspath(bin_dir)
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    path = os.path.join(bin_dir, "oracle_ask.py")
    spec = importlib.util.spec_from_file_location("oracle_ask_harness", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clopper_pearson_lo(k, n, alpha=0.05):
    if n == 0:
        return 0.0
    if k == 0:
        return 0.0
    # exact lower bound via beta quantile; bisection fallback-free
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        # P(Bin(n, mid) >= k)
        s = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i)
                for i in range(k, n + 1))
        if s > alpha:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def run_harness(mode, bin_dir, timeout_s, out_path):
    ask = load_oracle_ask(bin_dir)
    if mode == "old":
        models = OLD_MODELS

        def slot_fn(m, prompt):
            jp, _att = ask.judge_once(m, prompt, timeout_s)
            return jp, {"slot": m, "served_by": m, "refused": jp.refused,
                        "valid": jp.valid,
                        "failure_category": jp.failure_category,
                        "attempts": 1}
    elif mode == "new":
        models = NEW_MODELS

        def slot_fn(m, prompt):
            jp, slot, attempts = ask._resilient_judge(m, prompt, timeout_s)
            slot["attempts"] = len(attempts)
            return jp, slot
    else:
        raise SystemExit("mode must be old|new")

    rows = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=len(models)) as ex:
        futs = {}
        for qi, q in enumerate(QUESTIONS):
            prompt = make_prompt(q)
            for m in models:
                futs[ex.submit(slot_fn, m, prompt)] = (qi, q, m)
        # No outer timeout: slots are self-bounded by _resilient_judge's
        # own per-attempt ceilings (primary + retry + local fallback).
        for fut in cf.as_completed(futs):
            qi, q, m = futs[fut]
            try:
                jp, slot = fut.result(timeout=timeout_s * 3 + 60)
                rows.append({
                    "question_idx": qi, "question": q,
                    "slot": slot.get("slot", m),
                    "served_by": slot.get("served_by", m),
                    "refused": bool(jp.refused),
                    "failure_category": slot.get("failure_category"),
                    "attempts": slot.get("attempts", 1),
                    "posterior": None if jp.refused else jp.posterior,
                    "latency_s": round(getattr(jp, "latency_s", 0) or 0, 2),
                    "error": getattr(jp, "error", None),
                })
            except Exception as e:
                rows.append({
                    "question_idx": qi, "question": q, "slot": m,
                    "served_by": m, "refused": True, "posterior": None,
                    "latency_s": 0, "error": "harness: %s" % e,
                })
    rows.sort(key=lambda r: (r["question_idx"], r["slot"]))
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    live = sum(1 for r in rows if not r["refused"])
    n = len(rows)
    rate = live / n if n else 0.0
    lo = clopper_pearson_lo(live, n)
    per_model = {}
    for m in models:
        mr = [r for r in rows if r["slot"] == m]
        ml = sum(1 for r in mr if not r["refused"])
        per_model[m] = {"live": ml, "n": len(mr),
                        "rate": round(ml / len(mr), 3) if mr else 0.0}
    summary = {
        "mode": mode, "questions": len(QUESTIONS), "slots_per_question": len(models),
        "timeout_s": timeout_s, "live": live, "n": n,
        "return_rate": round(rate, 4),
        "cp_lower_bound_95": round(lo, 4),
        "elapsed_s": round(time.time() - t0, 1),
        "per_model": per_model, "out": out_path,
    }
    print(json.dumps(summary, indent=2))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", required=True, choices=["old", "new"])
    ap.add_argument("--bin-dir", required=True)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    run_harness(args.mode, args.bin_dir, args.timeout, args.out)


if __name__ == "__main__":
    main()
