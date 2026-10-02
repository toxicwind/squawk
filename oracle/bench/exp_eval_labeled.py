#!/usr/bin/env python3
"""Experiment 1+5(partial): labeled accuracy-vs-outcomes eval for the Oracle.

Runs oracle_ask.run_ask end-to-end over a labeled question set (default:
bench/eval_questions.jsonl, N=100 resolved KalshiBench questions) and
scores the engine against ground truth.

Measures:
  - verdict accuracy, Brier score, NLL -- overall and per tier
    (AUTO / VOTE / DEBATE / HUMAN / escalated / refused)
  - calibration: predicted-vs-empirical bins + ECE
  - per-judge accuracy/Brier/NLL/return-rate (the pooled-vs-single delta
    is the engine's value-add signal)
  - pooled vs mean-judge vs hard-majority
  - co-failure beta: all-live-judges-wrong rate + Clopper-Pearson bound
    on the 1-beta ensemble ceiling (engine's own cal.clopper_pearson,
    two-sided convention -- the same function that gates emissions)
  - escalation distribution: tier counts, withheld counts, HUMAN flags
  - latency p50/p95 per tier + phase splits (frame/judge/engine/debate)
    from the verdict timing field
  - cost per tier: code-accounted $/verdict AND measured upstream
    $/verdict (herd usage.cost sums; free-tier judges report 0)

Measurement conditions (identical for any baseline-vs-new comparison):
  - ORACLE_WORK points at a per-run SCRATCH dir: cold calibrators
    (identity maps), cold abstention gate (unanimity bar), eval verdicts
    never touch the production ledger.
  - Fixed: timeout 90s, budget 240s, models = oracle-judge-a/b/c,
    concurrency C (recorded). Herd panel aliases->targets snapshotted
    from config/herd.yaml into the summary.
  - Judge flakiness is recorded, not hidden: per-slot live/refused,
    attempts, and the global return rate with a CP bound.

Writes (under bench/results/):
  eval_<ts>.jsonl          one row per question (full verdict fields)
  eval_<ts>_summary.json   metrics + conditions + caveats

Usage:
  python3 bench/exp_eval_labeled.py [--questions bench/eval_questions.jsonl]
      [--concurrency 4] [--timeout 90] [--budget 240] [--limit 0]
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import random
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "bin")
RESULTS = os.path.join(HERE, "results")


def ask_text(q):
    t = q["question"].strip()
    if q.get("resolution_date"):
        t += " Resolution date: %s." % q["resolution_date"]
    c = (q.get("criteria") or "").strip()
    if c:
        t += " Resolution criterion: " + c
    return t


def load_panel_snapshot():
    """Alias -> concrete target from config/herd.yaml (conditions record)."""
    snap = {}
    path = "/home/toxic/estate/config/herd.yaml"
    try:
        with open(path) as f:
            txt = f.read()
        for alias in ("oracle-judge-a", "oracle-judge-b",
                      "oracle-judge-c", "oracle-judge-local"):
            m = re.search(re.escape(alias) + r":\s*\n\s*cmd:[^\n]*--target\s+(\S+)",
                          txt)
            if m:
                snap[alias] = m.group(1)
    except Exception as e:
        snap["_error"] = str(e)
    return snap


def pct(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def summarize_question(q, verdict, elapsed, escalation_mod):
    """Flatten one verdict into an eval row.

    escalation_mod: the imported escalation module (for policy-tier
    computation with gate_ok=True, independent of cold-start history).
    """
    contribs = {c["judge"]: c for c in
                (verdict.get("judge_contributions") or [])}
    models = verdict.get("models") or []
    judges = []
    for m in models:
        slot = next((s for s in (verdict.get("judge_slots") or [])
                     if s.get("slot") == m), {})
        served = slot.get("served_by", m)
        refused = bool(slot.get("refused", True))
        c = contribs.get(served) if not refused else None
        lat = (verdict.get("judge_latencies") or {}).get(m)
        judges.append({
            "slot": m, "served_by": served, "refused": refused,
            "attempts": slot.get("attempts", 1),
            "posterior": (c or {}).get("posterior"),
            "weight": (c or {}).get("weight"),
            "latency_s": lat,
        })
    conf = (verdict.get("structural_confidence") or {}).get("confidence")
    live_posts = [j["posterior"] for j in judges
                  if not j["refused"] and j["posterior"] is not None]
    if live_posts and conf is not None:
        policy_tier, policy_tier_reason = escalation_mod.route(
            live_posts, conf, True)
    else:
        policy_tier, policy_tier_reason = None, "no live judges/posterior"
    row = {
        "eval_id": q["eval_id"], "kb_id": q.get("kb_id"),
        "category": q.get("category"), "label": q["label"],
        "question": ask_text(q),
        "status": verdict.get("status"), "tier": verdict.get("tier"),
        "tier_reason": verdict.get("tier_reason"),
        "policy_tier": policy_tier,
        "policy_tier_reason": policy_tier_reason,
        "probability": verdict.get("probability"),
        "prior": verdict.get("prior"),
        "gate_reason": verdict.get("gate_reason"),
        "structural_confidence": conf,
        "judges": judges,
        "n_live": sum(1 for j in judges if not j["refused"]),
        "latency_s": verdict.get("latency_s", elapsed),
        "timing": verdict.get("timing") or {},
        "llm_calls": verdict.get("llm_calls"),
        "cost_usd": verdict.get("cost_usd"),
        "usage_cost_usd": verdict.get("usage_cost_usd"),
        "debate": ({k: v for k, v in (verdict.get("debate") or {}).items()
                    if k in ("rounds", "converged", "vote_probability",
                             "vote_status", "vote_tier")}
                   if verdict.get("debate") else None),
        "canary_flags": verdict.get("canary_flags"),
        "verdict_sha256": verdict.get("verdict_sha256"),
    }
    return row


def brier_nll_acc(rows):
    ps = [r["probability"] for r in rows]
    ys = [r["label"] for r in rows]
    brier = mean([(p - y) ** 2 for p, y in zip(ps, ys)])
    nll = mean([-(y * math.log(max(p, 1e-9)) +
                    (1 - y) * math.log(max(1 - p, 1e-9)))
                for p, y in zip(ps, ys)])
    acc = mean([1.0 if (p >= 0.5) == bool(y) else 0.0
                for p, y in zip(ps, ys)])
    return {"n": len(rows), "accuracy": acc, "brier": brier, "nll": nll}


def calibration_bins(rows, nbins=10):
    bins = [{"lo": i / nbins, "hi": (i + 1) / nbins, "ps": [], "ys": []}
            for i in range(nbins)]
    for r in rows:
        p = r["probability"]
        i = min(nbins - 1, int(p * nbins))
        bins[i]["ps"].append(p)
        bins[i]["ys"].append(r["label"])
    out = []
    ece = 0.0
    n = len(rows)
    for b in bins:
        cnt = len(b["ps"])
        mp = mean(b["ps"]) if cnt else None
        er = mean(b["ys"]) if cnt else None
        gap = abs(mp - er) if cnt else None
        if cnt:
            ece += (cnt / n) * gap
        out.append({"bin": [b["lo"], b["hi"]], "count": cnt,
                    "mean_predicted": mp, "empirical_rate": er, "gap": gap})
    return {"bins": out, "ece": ece}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions",
                    default=os.path.join(HERE, "eval_questions.jsonl"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--budget", type=float, default=240)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--question-delay", type=float, default=0,
                    help="seconds to wait between questions (free-tier pacing; "
                         "eval methodology only, not production behavior)")
    a = ap.parse_args(argv)

    ts = int(time.time())
    tag = ("-" + a.tag) if a.tag else ""
    work = "/home/toxic/estate/projects/range/ranch/oracle/work-eval-%d%s" % (ts, tag)
    os.makedirs(work, exist_ok=True)
    os.environ["ORACLE_WORK"] = work

    sys.path.insert(0, BIN)
    import oracle_ask
    import calibration as cal
    import escalation as esc_mod

    with open(a.questions) as f:
        questions = [json.loads(l) for l in f if l.strip()]
    if a.limit:
        questions = questions[:a.limit]
    rng = random.Random(20260920)

    os.makedirs(RESULTS, exist_ok=True)
    rows_path = os.path.join(RESULTS, "eval_%d%s.jsonl" % (ts, tag))
    sum_path = os.path.join(RESULTS, "eval_%d%s_summary.json" % (ts, tag))
    gitsha = subprocess.run(["git", "-C", "/home/toxic/estate",
                             "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()

    t_run0 = time.time()
    rows = []

    def one(q):
        # Panel-only: allow_debate=False. Debates run separately on
        # policy-DEBATE rows (escalation counterfactual harness), keeping
        # panel call volume at 3 judges/question.
        time.sleep(rng.uniform(0, 1.5))  # stagger: no thundering herd
        t0 = time.time()
        try:
            v = oracle_ask.run_ask(ask_text(q), timeout_s=a.timeout,
                                   budget_s=a.budget, allow_debate=False)
        except Exception as e:  # never lose the row; record the failure
            v = {"status": "harness_error", "tier": None,
                 "probability": None, "error": "%s: %s" % (type(e).__name__, e),
                 "latency_s": time.time() - t0}
        r = summarize_question(q, v, time.time() - t0, esc_mod)
        if a.question_delay:
            time.sleep(a.question_delay)
        return r

    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(one, q): q for q in questions}
        done = 0
        with open(rows_path, "w") as f:
            for fut in cf.as_completed(futs):
                r = fut.result()
                rows.append(r)
                f.write(json.dumps(r, default=str) + "\n")
                f.flush()
                done += 1
                if done % 10 == 0:
                    print("  %d/%d questions (%.0fs)" %
                          (done, len(questions), time.time() - t_run0),
                          flush=True)
    rows.sort(key=lambda r: r["eval_id"])

    # ---- metrics ----
    # SCORABLE: every row bearing a probability (even if cold-gate withheld).
    # EMITTED: the subset the gate actually released (status == verdict).
    scorable = [r for r in rows if r["probability"] is not None]
    emitted = [r for r in scorable if r["status"] == "verdict"]
    overall_scorable = brier_nll_acc(scorable) if scorable else {"n": 0}
    overall_emitted = brier_nll_acc(emitted) if emitted else {"n": 0}

    # Per policy tier (disagreement-only routing, gate_ok=True) on scorable.
    by_policy = {}
    for r in scorable:
        by_policy.setdefault(r["policy_tier"] or "?", []).append(r)
    policy_tier_metrics = {t: brier_nll_acc(rs)
                           for t, rs in by_policy.items()}
    # Per reported tier on emitted (cold-gate behavior).
    by_tier = {}
    for r in emitted:
        by_tier.setdefault(r["tier"] or "?", []).append(r)
    tier_metrics = {t: brier_nll_acc(rs) for t, rs in by_tier.items()}
    # Calibration bins on scorable (all forecasts) and emitted.
    calib_scorable = calibration_bins(scorable) if scorable else {"ece": None}
    calib_emitted = calibration_bins(emitted) if emitted else {"ece": None}
    # Cold-gate withholding.
    gate_stats = {
        "n_rows": len(rows), "n_scorable": len(scorable),
        "n_emitted": len(emitted),
        "withholding_rate": (1 - len(emitted) / len(scorable)
                             if scorable else None),
    }

    # per-judge (by panel slot)
    judge_stats = {}
    for r in rows:
        for j in r["judges"]:
            s = judge_stats.setdefault(j["slot"],
                                       {"live": 0, "slots": 0, "ps": [],
                                        "ys": [], "lat": [], "attempts": []})
            s["slots"] += 1
            s["attempts"].append(j["attempts"])
            if not j["refused"] and j["posterior"] is not None:
                s["live"] += 1
                s["ps"].append(j["posterior"])
                s["ys"].append(r["label"])
                if j["latency_s"]:
                    s["lat"].append(j["latency_s"])
    for alias, s in judge_stats.items():
        lo, hi = cal.clopper_pearson(s["live"], s["slots"], 0.05)
        s["return_rate"] = s["live"] / s["slots"] if s["slots"] else 0
        s["return_cp_lo"] = lo
        s["return_cp_hi"] = hi
        if s["ps"]:
            s.update(brier_nll_acc(
                [{"probability": p, "label": y}
                 for p, y in zip(s["ps"], s["ys"])]))
            s["median_latency_s"] = pct(sorted(s["lat"]), 0.5)
        s["mean_attempts"] = mean(s["attempts"])
        del s["ps"], s["ys"], s["lat"], s["attempts"]

    # pooled vs mean-judge vs hard majority (SCORABLE, >=2 live judges)
    multi = [r for r in scorable if r["n_live"] >= 2]
    def agg_metrics(aggfn, name):
        ps = [aggfn(r) for r in multi]
        return {"name": name, **brier_nll_acc(
            [{"probability": p, "label": r["label"]}
             for p, r in zip(ps, multi)])}
    agg_cmp = [
        agg_metrics(lambda r: r["probability"], "pooled_engine"),
        agg_metrics(lambda r: mean([j["posterior"] for j in r["judges"]
                                    if not j["refused"]]), "mean_judge"),
        agg_metrics(lambda r: 0.75 if sum(
            1 for j in r["judges"]
            if not j["refused"] and j["posterior"] >= 0.5) > r["n_live"] / 2
            else 0.25, "hard_majority"),
    ]

    # co-failure beta: all live judges wrong (SCORABLE, >=2 live).
    # beta = P(all live judges wrong); 1-beta is the ensemble ceiling:
    # no aggregation of this panel can beat it (if every judge is wrong,
    # every convex combination is wrong). Exact two-sided Clopper-Pearson
    # bounds throughout (production calibration.clopper_pearson).
    cofail = [r for r in multi
              if all(((j["posterior"] >= 0.5) != bool(r["label"]))
                     for j in r["judges"] if not j["refused"])]
    k, n = len(cofail), len(multi)
    blo, bhi = cal.clopper_pearson(k, n, 0.05)
    beta = {"n": n, "cofailures": k, "beta": k / n if n else None,
            "beta_cp_lo": blo, "beta_cp_hi": bhi,
            "ceiling_1_minus_beta": 1 - k / n if n else None,
            "ceiling_cp_lo": 1 - bhi if n else None,
            "ceiling_cp_hi": 1 - blo if n else None,
            "cofailure_ids": [r["eval_id"] for r in cofail]}

    # escalation distribution (all rows incl. non-emitted)
    tiers = {}
    for r in rows:
        tiers[r["tier"] or "none"] = tiers.get(r["tier"] or "none", 0) + 1
    statuses = {}
    for r in rows:
        statuses[r["status"] or "?"] = statuses.get(r["status"] or "?", 0) + 1

    # latency / cost per tier (emitted)
    lat, cost = {}, {}
    for t, rs in by_tier.items():
        ls = [r["latency_s"] for r in rs if r["latency_s"]]
        lat[t] = {"n": len(ls), "p50": pct(ls, 0.5), "p95": pct(ls, 0.95),
                  "mean": mean(ls),
                  "judge_s_p50": pct([r["timing"].get("judge_s") for r in rs
                                      if r["timing"].get("judge_s")], 0.5),
                  "engine_s_p50": pct([r["timing"].get("engine_s") for r in rs
                                       if r["timing"].get("engine_s")], 0.5),
                  "debate_s_p50": pct([r["timing"].get("debate_s") for r in rs
                                       if r["timing"].get("debate_s")], 0.5)}
        calls = [r["llm_calls"] for r in rs if r["llm_calls"] is not None]
        cods = [r["cost_usd"] for r in rs if r["cost_usd"] is not None]
        usos = [r["usage_cost_usd"] for r in rs
                if r["usage_cost_usd"] is not None]
        cost[t] = {"n": len(rs), "mean_llm_calls": mean(calls),
                   "mean_cost_usd_accounted": mean(cods),
                   "mean_usage_cost_usd_measured": mean(usos)}

    # judge return overall (slot-level)
    tot_live = sum(s["live"] for s in judge_stats.values())
    tot_slots = sum(s["slots"] for s in judge_stats.values())
    rlo, rhi = cal.clopper_pearson(tot_live, tot_slots, 0.05)

    summary = {
        "ts": ts, "tag": a.tag,
        "rows_path": rows_path,
        "conditions": {
            "git_sha": gitsha,
            "repo": "toxicwind/sovereign-projects",
            "question_source": "2084Collective/kalshibench-v2 via datasets-server API",
            "eval_set": a.questions,
            "sample_seed": 20260920,
            "n_questions": len(questions),
            "herd_panel": load_panel_snapshot(),
            "timeout_s": a.timeout, "budget_s": a.budget,
            "concurrency": a.concurrency,
            "question_delay_s": a.question_delay,
            "oracle_work": work + " (SCRATCH: cold calibrators=identity, "
                           "cold abstention gate=unanimity bar, eval "
                           "verdicts isolated from production ledger)",
            "judge_return": {"live": tot_live, "slots": tot_slots,
                             "rate": tot_live / tot_slots if tot_slots else 0,
                             "cp_lo": rlo, "cp_hi": rhi},
            "wall_s": round(time.time() - t_run0, 1),
        },
        "caveats": [
            "Questions resolved 2025-10/11, before herd judges' knowledge "
            "cutoff: judges may recall outcomes from training. This eval "
            "measures AGGREGATION fidelity (pooling+calibration+gating of "
            "judge posteriors), not forecasting skill on the unknown.",
            "Absolute accuracy is NOT comparable to cutoff-filtered "
            "KalshiBench baselines; pooled-vs-single-judge deltas are the "
            "engine's value-add signal.",
            "Cold-start gate: verdicts emit only on unanimous "
            "high-confidence (struct>=0.90, posterior>=0.85 or <=0.15); "
            "non-unanimous verdicts are withheld (status=escalate) by "
            "design, not by failure.",
            "CP intervals use calibration.py's two-sided exact "
            "clopper_pearson -- the same function that gates emissions. "
            "(docs/oracle-core.md's 0.6366 for 13/15 used bench/judge_return.py's "
            "one-sided bisection; not the same convention.)",
        ],
        "n_rows": len(rows), "n_scorable": len(scorable),
        "n_emitted": len(emitted),
        "gate": gate_stats,
        "statuses": statuses, "tiers": tiers,
        "policy_tiers": {t: len(rs) for t, rs in by_policy.items()},
        "overall_scorable": overall_scorable,
        "overall_emitted": overall_emitted,
        "per_policy_tier": policy_tier_metrics,
        "per_tier_emitted": tier_metrics,
        "calibration_scorable": calib_scorable,
        "calibration_emitted": calib_emitted,
        "judge_stats": judge_stats,
        "aggregation_comparison": agg_cmp,
        "cofailure_beta": beta,
        "latency_per_tier": lat,
        "cost_per_tier": cost,
    }
    with open(sum_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print("rows: %s" % rows_path)
    print("summary: %s" % sum_path)
    print(json.dumps({"overall_scorable": summary["overall_scorable"],
                      "overall_emitted": summary["overall_emitted"],
                      "policy_tiers": summary["policy_tiers"],
                      "tiers": tiers, "statuses": statuses,
                      "beta": {k: beta[k] for k in
                               ("n", "cofailures", "beta", "ceiling_cp_lo")}},
                     indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main(sy