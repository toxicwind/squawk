#!/usr/bin/env python3
"""Experiment 2: escalation analysis -- is disagreement the right trigger?

Two counterfactual measurements on the labeled eval rows:

1. DEBATE-escalated rows: did the debate actually matter? Compare the
   pre-debate vote verdict (saved in the eval row) with the post-debate
   final: |delta_p|, side flips (0.5 crossing), correctness flips vs the
   label. Escalation precision = P(debate mattered | escalated).

2. AUTO/VOTE rows (seeded sample, default n=25): would a debate have
   mattered? Runs the production debate path (escalation.debate_tier +
   engine re-aggregation with half-weight advocate finals -- the same
   code run_ask uses) on questions the ladder did NOT escalate, then
   compares the counterfactual final against the emitted verdict.
   Recall proxy = P(debate would have mattered | not escalated).

"mattered" is reported at three thresholds: |delta_p| >= 0.05,
side flip, correctness flip. The verdict on the trigger uses the
correctness-flip rate: escalation is worth its cost only if it changes
outcomes, not just decimals.

Caveat (documented in output): counterfactual debates run with empty
evidence text -- judge claims were not persisted in eval rows. Question,
criteria, panel aliases, k/rounds/eps/timeouts are identical to the
production debate path. Debate is stochastic (temperature 0.2); one run
per question.

Writes: bench/results/escalation_<ts>.json
Usage: python3 bench/exp_escalation_counterfactual.py
         --rows bench/results/eval_<ts>.jsonl [--n-counter 25]
         [--concurrency 4]
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

MODELS = ["oracle-judge-a", "oracle-judge-b", "oracle-judge-c"]


def debated_final(question_text, timeout_s=90.0, work=None):
    """Mirror of oracle_ask.run_ask's debate block (same code path)."""
    import framing, engine, escalation, oracle_ask
    framed = framing.frame_question(question_text)
    if framed.get("status") == "refused":
        return None, "framing_refused"
    usages = []

    def _chat(model, prompt, t):
        res = oracle_ask.herd_chat(model, prompt, t, max_tokens=400)
        usages.append(res.get("usage") or {})
        return {"content": res.get("text") or ""}

    t0 = time.time()
    debate = escalation.debate_tier(
        framed["binary_question"], framed["resolution_criteria"], "",
        judges=list(MODELS), chat_fn=_chat,
        k=escalation.DEBATE_K, max_rounds=escalation.DEBATE_MAX_ROUNDS,
        eps=escalation.DEBATE_EPS, per_advocate_timeout_s=timeout_s)
    adv = [engine.JudgePosterior(judge_id=a["model"],
                                 posterior=a["posterior"], cal_weight=0.5)
           for a in debate["advocate_finals"]]
    final = engine.build_verdict(framed, adv)
    return {"p": final.get("probability"), "status": final.get("status"),
            "rounds": debate["rounds"], "converged": debate["converged"],
            "requests": debate.get("requests", 0),
            "latency_s": round(time.time() - t0, 1),
            "advocate_finals": debate["advocate_finals"]}, None


def mattered(p_before, p_after, label):
    if p_before is None or p_after is None:
        return {"dp": None, "side_flip": None, "correct_flip": None}
    dp = abs(p_after - p_before)
    side_flip = (p_before >= 0.5) != (p_after >= 0.5)
    c_before = (p_before >= 0.5) == bool(label)
    c_after = (p_after >= 0.5) == bool(label)
    return {"dp": round(dp, 4), "side_flip": side_flip,
            "correct_flip": c_before != c_after,
            "improved": (not c_before) and c_after,
            "worsened": c_before and (not c_after)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--n-counter", type=int, default=25)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260920)
    a = ap.parse_args(argv)

    ts = int(time.time())
    work = "/home/toxic/estate/projects/range/ranch/oracle/work-escal-%d" % ts
    os.makedirs(work, exist_ok=True)
    os.environ["ORACLE_WORK"] = work
    sys.path.insert(0, BIN)

    with open(a.rows) as f:
        rows = [json.loads(l) for l in f if l.strip()]

    # ---- part 1: policy-DEBATE rows -- run the production debate path
    # and compare the debate final against the panel vote.
    # (Eval rows were panel-only, allow_debate=False, so debates run here.)
    debate_cand = [r for r in rows
                   if r.get("policy_tier") == "DEBATE"
                   and r["probability"] is not None and r["n_live"] >= 2]
    rng = random.Random(a.seed)
    rng.shuffle(debate_cand)
    debate_sample = debate_cand[:a.n_counter]
    part1 = []

    def one_debate(r):
        t0 = time.time()
        try:
            time.sleep(rng.uniform(0, 1.5))
            fin, err = debated_final(r["question"])
        except Exception as e:
            fin, err = None, "%s: %s" % (type(e).__name__, e)
        m = mattered(r["probability"], (fin or {}).get("p"), r["label"])
        return {"eval_id": r["eval_id"], "label": r["label"],
                "policy_tier": r["policy_tier"],
                "p_vote": r["probability"],
                "debate": fin, "error": err,
                "wall_s": round(time.time() - t0, 1), **m}

    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = [ex.submit(one_debate, r) for r in debate_sample]
        for i, fut in enumerate(cf.as_completed(futs)):
            part1.append(fut.result())
            if (i + 1) % 5 == 0:
                print("  debate %d/%d" % (i + 1, len(debate_sample)),
                      flush=True)
    part1.sort(key=lambda x: x["eval_id"])

    # ---- part 2: counterfactual debates on policy-AUTO/VOTE sample ----
    cand = [r for r in rows if r.get("policy_tier") in ("AUTO", "VOTE")
            and r["probability"] is not None and r["n_live"] >= 2]
    rng.shuffle(cand)
    sample = cand[:a.n_counter]
    part2 = []

    def one(r):
        t0 = time.time()
        try:
            time.sleep(rng.uniform(0, 1.5))
            fin, err = debated_final(r["question"])
        except Exception as e:
            fin, err = None, "%s: %s" % (type(e).__name__, e)
        m = mattered(r["probability"], (fin or {}).get("p"), r["label"])
        return {"eval_id": r["eval_id"], "label": r["label"],
                "policy_tier": r["policy_tier"], "p_vote": r["probability"],
                "counter": fin, "error": err,
                "wall_s": round(time.time() - t0, 1), **m}

    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = [ex.submit(one, r) for r in sample]
        for i, fut in enumerate(cf.as_completed(futs)):
            part2.append(fut.result())
            if (i + 1) % 5 == 0:
                print("  counterfactual %d/%d" % (i + 1, len(sample)), flush=True)
    part2.sort(key=lambda x: x["eval_id"])

    def rate(items, key):
        xs = [x for x in items if x.get(key) is not None]
        return {"n": len(xs),
                "rate": sum(1 for x in xs if x[key]) / len(xs) if xs else None}

    out = {
        "ts": ts, "rows_path": a.rows, "oracle_work": work,
        "conditions": {
            "policy_tier_source": "eval rows' policy_tier (route with "
                                  "gate_ok=True, disagreement-only)",
            "debate_path": "escalation.debate_tier + engine re-aggregation "
                           "(half-weight advocate finals), same as run_ask",
            "n_debate_sample": len(debate_sample),
            "n_counter_sample": len(sample),
            "seed": a.seed, "concurrency": a.concurrency,
        },
        "caveats": [
            "Counterfactual debates run with EMPTY evidence text (judge "
            "claims were not persisted in eval rows); question, criteria, "
            "panel aliases, k/rounds/eps/timeouts match the production "
            "debate path exactly.",
            "Debate is stochastic (temperature 0.2); one run per question.",
            "Part 1 runs the debate live on policy-DEBATE rows (panel eval "
            "used allow_debate=False); Part 2 runs it on policy-AUTO/VOTE "
            "rows as the counterfactual.",
        ],
        "part1_debate_escalated": {
            "n": len(part1),
            "dp_ge_05": rate(part1, "dp") and {
                "n": len([x for x in part1 if x["dp"] is not None]),
                "rate": sum(1 for x in part1
                            if x["dp"] is not None and x["dp"] >= 0.05) /
                        max(1, len([x for x in part1 if x["dp"] is not None]))},
            "side_flip": rate(part1, "side_flip"),
            "correct_flip": rate(part1, "correct_flip"),
            "improved": rate(part1, "improved"),
            "worsened": rate(part1, "worsened"),
            "items": part1,
        },
        "part2_counterfactual": {
            "n_sampled": len(part2),
            "dp_ge_05": {
                "n": len([x for x in part2 if x["dp"] is not None]),
                "rate": sum(1 for x in part2
                            if x["dp"] is not None and x["dp"] >= 0.05) /
                        max(1, len([x for x in part2 if x["dp"] is not None]))},
            "side_flip": rate(part2, "side_flip"),
            "correct_flip": rate(part2, "correct_flip"),
            "improved": rate(part2, "improved"),
            "worsened": rate(part2, "worsened"),
            "mean_counter_latency_s": (
                sum(x["wall_s"] for x in part2) / len(part2) if part2 else None),
            "items": part2,
        },
    }
    # verdict on the trigger (correctness-flip criterion)
    p1 = out["part1_debate_escalated"]["correct_flip"]["rate"]
    p2 = out["part2_counterfactual"]["correct_flip"]["rate"]
    out["verdict_on_trigger"] = {
        "escalation_precision_correct_flip": p1,
        "nonescalated_counterfactual_correct_flip": p2,
        "interpretation":
            "If p1 >> p2, disagreement-triggered debate buys correctness "
            "that auto-resolution leaves on the table: the trigger is "
            "right. If p1 ~= p2, debate changes outcomes at the same rate "
            "whether or not the ladder fired: the trigger adds cost "
            "without discrimination.",
    }
    path = os.path.join(RESULTS, "escalation_%d.json" % ts)
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("wrote %s" % path)
    print(json.dumps({k: out[k] for k in
                      ("part1_debate_escalated", "part2_counterfactual")
                      if k in out}, indent=2, default=str)[:1500])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
