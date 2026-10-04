#!/usr/bin/env python3
"""Experiment 3: latency & cost per tier -- where does the time/money go.

Part A (offline, from eval rows): phase-split analysis (frame / judge /
engine / debate medians), per-judge latency distribution, llm_calls
histogram per tier, accounted vs measured cost per tier.

Part B (live): concurrency sweep. A seeded 12-question subset is asked at
C = 1, 2, 4, 8 concurrent run_ask calls: wall time, per-question latency
p50, judge return rate, refusal rate. Finds the knee where free-tier
flakiness starts costing more than the parallelism saves.

Part C (offline ablations on saved eval posteriors -- no new LLM calls):
  C1 drop-slowest-judge: re-pool each emitted verdict from its live judges
     minus the max-latency one via engine.pooled_posterior (identity
     calibration, same as the cold eval) -> Brier/accuracy delta vs full
     panel. Answers: is the slowest judge worth the wait?
  C2 skip-debate: for DEBATE rows, score the saved vote_probability as the
     verdict -> accuracy/Brier delta and llm_calls saved vs the debate
     final. Answers: what does the debate buy per request?

The "cheapest cut that doesn't move accuracy" is the ablation with the
largest latency/cost saving at |accuracy delta| within noise.

Writes: bench/results/latency_cost_<ts>.json
Usage: python3 bench/exp_latency_cost.py --rows bench/results/eval_<ts>.jsonl
         [--sweep] [--concurrency-list 1,2,4,8]
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "bin")
RESULTS = os.path.join(HERE, "results")


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def part_a(rows):
    # Scorable rows (all forecasts); policy tiers for the breakdown.
    # (Cold-gate emits few verdicts; the latency/cost profile is the
    # panel's, not the gate's.)
    scorable = [r for r in rows if r["probability"] is not None]
    phases = {}
    for ph in ("frame_s", "judge_s", "engine_s", "debate_s"):
        vals = [r["timing"].get(ph) for r in scorable]
        phases[ph] = {"p50": pct(vals, 0.5), "p95": pct(vals, 0.95),
                      "mean": mean(vals),
                      "n": len([v for v in vals if v is not None])}
    per_tier = {}
    for r in scorable:
        t = r["policy_tier"] or "?"
        d = per_tier.setdefault(t, {"lat": [], "calls": [],
                                    "acct": [], "meas": []})
        d["lat"].append(r["latency_s"])
        d["calls"].append(r["llm_calls"])
        d["acct"].append(r["cost_usd"])
        d["meas"].append(r["usage_cost_usd"])
    for t, d in per_tier.items():
        per_tier[t] = {k: {"p50": pct(v, 0.5), "p95": pct(v, 0.95),
                           "mean": mean(v)} for k, v in d.items()}
    # per-judge latency: which slot is usually slowest?
    slowest = {}
    for r in scorable:
        live = [(j["slot"], j["latency_s"]) for j in r["judges"]
                if not j["refused"] and j["latency_s"]]
        if len(live) >= 2:
            s = max(live, key=lambda x: x[1])[0]
            slowest[s] = slowest.get(s, 0) + 1
    return {"phase_splits": phases, "per_tier": per_tier,
            "slowest_judge_counts": slowest, "n_emitted": len(scorable)}


def part_b(questions_path, concurrencies, seed):
    sys.path.insert(0, BIN)
    import oracle_ask
    with open(questions_path) as f:
        qs = [json.loads(line) for line in f if line.strip()]
    rng = random.Random(seed)
    rng.shuffle(qs)
    sub = qs[:12]
    res = {}
    for c in concurrencies:
        work = ("/home/toxic/estate/ranch/squawk/oracle/"
                "work-sweep-c%d-%d" % (c, int(time.time())))
        os.makedirs(work, exist_ok=True)
        os.environ["ORACLE_WORK"] = work
        # reimport to pick up the new ORACLE_WORK is unnecessary:
        # engine/oracle_ask read it at first import; force reload
        import importlib
        import engine
        importlib.reload(engine)
        importlib.reload(oracle_ask)
        lat, refused, slots_live, slots_tot = [], 0, 0, 0

        def one(q):
            t0 = time.time()
            txt = q["question"].strip()
            if q.get("resolution_date"):
                txt += " Resolution date: %s." % q["resolution_date"]
            txt += " Resolution criterion: " + (q.get("criteria") or "").strip()
            try:
                v = oracle_ask.run_ask(txt, timeout_s=90, budget_s=240)
            except Exception:
                return None
            el = time.time() - t0
            live = sum(1 for s in (v.get("judge_slots") or [])
                       if not s.get("refused"))
            return el, live, len(v.get("judge_slots") or []), v.get("status")

        t0 = time.time()
        with cf.ThreadPoolExecutor(max_workers=c) as ex:
            futs = [ex.submit(one, q) for q in sub]
            outs = [f.result() for f in cf.as_completed(futs)]
        wall = time.time() - t0
        outs = [o for o in outs if o]
        for el, live, tot, st in outs:
            lat.append(el)
            slots_live += live
            slots_tot += tot
            if st not in ("verdict", "escalate"):
                refused += 1
        res["C%d" % c] = {"wall_s": round(wall, 1),
                          "per_q_latency_p50": pct(lat, 0.5),
                          "n_done": len(outs),
                          "judge_return": (slots_live / slots_tot
                                           if slots_tot else None),
                          "refused": refused}
        print("  C=%d wall=%.0fs p50=%.0fs return=%.2f" %
              (c, wall, pct(lat, 0.5) or 0,
               slots_live / slots_tot if slots_tot else 0), flush=True)
    return res


def part_c(rows):
    sys.path.insert(0, BIN)
    import engine
    # Scorable rows with 2+ live judges (cold-gate emits few verdicts;
    # the ablation is on the panel, not the gate).
    scorable = [r for r in rows if r["probability"] is not None
                and r["n_live"] >= 2]

    def metrics(items):
        acc = mean([1.0 if (p >= 0.5) == bool(y) else 0.0 for p, y in items])
        br = mean([(p - y) ** 2 for p, y in items])
        return {"n": len(items), "accuracy": acc, "brier": br}

    # C1: drop the slowest live judge per question, re-pool
    full, cut = [], []
    saved_lat, saved_calls = [], []
    for r in scorable:
        live = [j for j in r["judges"] if not j["refused"]
                and j["posterior"] is not None]
        if len(live) < 2:
            continue
        prior = r.get("prior", 0.5) or 0.5
        js = [engine.JudgePosterior(j["slot"], j["posterior"],
                                    cal_weight=(j.get("weight") or 1.0),
                                    reliability=1.0) for j in live]
        p_full, _ = engine.pooled_posterior(prior, js)
        full.append((p_full, r["label"]))
        slow = max(live, key=lambda j: j["latency_s"] or 0)
        rest = [j for j in live if j["slot"] != slow["slot"]]
        js2 = [engine.JudgePosterior(j["slot"], j["posterior"],
                                     cal_weight=(j.get("weight") or 1.0),
                                     reliability=1.0) for j in rest]
        p_cut, _ = engine.pooled_posterior(prior, js2)
        cut.append((p_cut, r["label"]))
        saved_lat.append((slow["latency_s"] or 0))
        saved_calls.append(1)  # ~1 judge call + its retries avoided
    c1 = {"full_panel": metrics(full), "drop_slowest": metrics(cut),
          "accuracy_delta": (metrics(cut)["accuracy"] or 0) -
                            (metrics(full)["accuracy"] or 0),
          "brier_delta": (metrics(cut)["brier"] or 0) -
                         (metrics(full)["brier"] or 0),
          "mean_latency_saved_s": mean(saved_lat)}

    # C2: debate value is measured live in exp_escalation_counterfactual
    # (Part 1: panel vote vs debate final on policy-DEBATE rows). Eval rows
    # were panel-only (allow_debate=False), so no saved debates exist here.
    c2 = {"n": 0, "note": "see escalation experiment Part 1"}
    return {"C1_drop_slowest_judge": c1, "C2_skip_debate": c2}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--questions",
                    default=os.path.join(HERE, "eval_questions.jsonl"))
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--concurrency-list", default="1,2,4,8")
    ap.add_argument("--seed", type=int, default=20260920)
    a = ap.parse_args(argv)
    ts = int(time.time())
    with open(a.rows) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    out = {"ts": ts, "rows_path": a.rows,
           "partA_phase_analysis": part_a(rows)}
    if a.sweep:
        out["partB_concurrency_sweep"] = part_b(
            a.questions, [int(x) for x in a.concurrency_list.split(",")],
            a.seed)
    out["partC_ablations"] = part_c(rows)
    # cheapest cut verdict
    c1 = out["partC_ablations"]["C1_drop_slowest_judge"]
    c2 = out["partC_ablations"]["C2_skip_debate"]
    out["cheapest_cut"] = {
        "C1_drop_slowest": {
            "latency_saved_s": c1["mean_latency_saved_s"],
            "accuracy_delta": c1["accuracy_delta"],
            "brier_delta": c1["brier_delta"]},
        "C2_skip_debate": {
            "latency_saved_s": c2["mean_debate_s"],
            "calls_saved": c2["mean_debate_calls"],
            "accuracy_delta": c2["accuracy_delta_vote_minus_debate"]},
        "rule": "largest saving wins among cuts with |accuracy_delta| "
                "within noise of 0 (noise ~= 1/sqrt(n) on accuracy)",
    }
    path = os.path.join(RESULTS, "latency_cost_%d.json" % ts)
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("wrote %s" % path)
    print(json.dumps({"partA": out["partA_phase_analysis"]["phase_splits"],
                      "cheapest_cut": out["cheapest_cut"]},
                     indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
