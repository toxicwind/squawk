#!/usr/bin/env python3
"""Build the Oracle labeled eval set from KalshiBench (HF: 2084Collective/kalshibench-v2).

Downloads all rows via the datasets-server API, then draws a stratified
seeded sample. Each row is a binary question: question text + description
as the resolution criterion, ground_truth yes/no as the label.

Why KalshiBench: 1,531 resolved real-world prediction-market questions with
verifiable outcomes -- the engine is scored against reality, not papers.
Documented caveat (also in the summary JSON): these questions resolved
2025-10/11, before the herd judges' knowledge cutoff, so judges may recall
outcomes from training. The eval therefore measures AGGREGATION fidelity
(pooling + calibration + gating of judge posteriors), not forecasting
skill on the unknown. Pooled-vs-single-judge deltas are the engine's
value-add signal; absolute accuracy is not comparable to cutoff-filtered
KalshiBench baselines.

Usage: python3 bench/build_eval_set.py [--n 100] [--seed 20260920]
Writes: bench/eval_questions.jsonl
"""
import argparse
import json
import random
import sys
import urllib.request

DS = "2084Collective%2Fkalshibench-v2"


def _api(off, page):
    return ("https://datasets-server.huggingface.co/rows?dataset=" + DS +
            "&config=default&split=train&offset=" + str(off) +
            "&length=" + str(page))


def fetch_all(page=100):
    rows = []
    off = 0
    total = None
    while True:
        with urllib.request.urlopen(_api(off, page), timeout=60) as r:
            d = json.load(r)
        if total is None:
            total = d["num_rows_total"]
            print("total rows: %d" % total, flush=True)
        batch = [x["row"] for x in d.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        off += len(batch)
        print("  fetched %d/%d" % (len(rows), total), flush=True)
        if len(rows) >= total or d.get("partial"):
            break
    return rows


def normalize(rows):
    out = []
    seen = set()
    for r in rows:
        q = (r.get("question") or "").strip()
        desc = (r.get("description") or "").strip()
        gt = (r.get("ground_truth") or "").strip().lower()
        if not q or gt not in ("yes", "no"):
            continue
        key = (q, desc)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "kb_id": r.get("id"),
            "question": q,
            "criteria": desc,
            "category": r.get("category") or "Unknown",
            "close_time": r.get("close_time"),
            "ground_truth": gt,
            "label": 1 if gt == "yes" else 0,
        })
    return out


def stratify(rows, n, seed):
    rng = random.Random(seed)
    # strata: ground_truth x category (top categories get proportional slots)
    cats = {}
    for r in rows:
        cats.setdefault((r["label"], r["category"]), []).append(r)
    # shuffle within strata
    for k in cats:
        rng.shuffle(cats[k])
    keys = sorted(cats)
    # round-robin across strata for balance
    picked = []
    idx = {k: 0 for k in keys}
    while len(picked) < n:
        progressed = False
        for k in keys:
            if idx[k] < len(cats[k]) and len(picked) < n:
                picked.append(cats[k][idx[k]])
                idx[k] += 1
                progressed = True
        if not progressed:
            break
    rng.shuffle(picked)
    for i, r in enumerate(picked):
        r["eval_id"] = "EV%03d" % (i + 1)
    return picked


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--out", default="bench/eval_questions.jsonl")
    ap.add_argument("--full-out", default=None,
                    help="optional path to dump all normalized rows")
    a = ap.parse_args(argv)
    rows = fetch_all()
    norm = normalize(rows)
    print("normalized binary rows: %d" % len(norm))
    if a.full_out:
        with open(a.full_out, "w") as f:
            for r in norm:
                f.write(json.dumps(r) + "\n")
        print("full dump: %s" % a.full_out)
    sample = stratify(norm, a.n, a.seed)
    with open(a.out, "w") as f:
        for r in sample:
            f.write(json.dumps(r) + "\n")
    # distribution report
    from collections import Counter
    print("sampled: %d (seed=%d)" % (len(sample), a.seed))
    print("label balance:", Counter(r["label"] for r in sample))
    print("categories:", Counter(r["category"] for r in sample))
    print("wrote %s" % a.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
