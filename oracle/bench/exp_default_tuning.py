#!/usr/bin/env python3
"""Experiment 4: default tuning with documented rationale.

Sweeps candidate defaults on the labeled eval set; every winner is chosen
by a measured delta, recorded in the output JSON. Production code is NOT
modified by this harness -- sweeps set module constants in-process only
(the harness's own process; the deployed defaults are untouched).

Sweeps:
  T1 unanimity bar AUTO_P in {0.80, 0.85, 0.90}: sweep the TIER-LADDER
     unanimity bar (escalation.route). The abstention gate no longer
     has a unanimity parameter -- the finite-sample CP bound governs
     emit/withhold at every n, and withholds at n=0 (no bypass)
     gate + escalation.route per eval row. Winner: min Brier on emitted,
     tie-break higher emission rate at accuracy >= 0.90.
  T2 escalation margin DISAGREE_MARGIN in {0.15, 0.25, 0.35}: the trigger
     as a classifier for "debate would change the outcome", labeled by
     bench/results/escalation_<ts>.json (E3). Winner: max F1.
  T3 judge panel size {2,3,4} (LIVE rerun, n=20 subset): models (a,b),
     (a,b,c), (a,b,c,local). Winner: min Brier; report latency/cost.
  T4 calibration loop per judge: 5-fold cross-fitted Platt vs isotonic vs
     raw on eval posteriors. Winner per judge: min NLL.
  T5 abstention (alpha, min_accuracy) in {0.01,0.05,0.10}x{0.75,0.80,0.85}:
     replay the gate rule (mirrors engine.abstention_gate exactly:
     CP lower bound >= min_acc on leave-one-out genuine-label
     histories, no label-count floor) from eval outcomes.
     Winner: max emission rate subject to emitted accuracy >= 0.90
     (frontier reported).
  T6 debate budget (k, rounds) in {(1,2),(1,3),(2,2),(2,3)} (LIVE rerun on
     DEBATE-tier subset, n<=12): final-p distance vs the (2,3) reference
     rerun. Winner: cheapest config with mean|dp| < 0.03 vs reference.

Writes: bench/results/tuning_<ts>.json  (tables + winner + rationale)
Usage: python3 bench/exp_default_tuning.py --rows bench/results/eval_<ts>.jsonl
         --escalation bench/results/escalation_<ts>.json
         [--live] [--concurrency 4]
Without --live, only offline sweeps (T1,T2,T4,T5) run.
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "bin")
RESULTS = os.path.join(HERE, "results")


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def acc_brier(items):
    acc = mean([1.0 if (p >= 0.5) == bool(y) else 0.0 for p, y in items])
    br = mean([(p - y) ** 2 for p, y in items])
    return {"n": len(items), "accuracy": acc, "brier": br}


def t1_unanimity_bar(rows):
    import escalation
    out = {}
    for bar in (0.80, 0.85, 0.90):
        escalation.AUTO_BAR = bar
        emitted, tiers = [], {}
        for r in rows:
            posts = [j["posterior"] for j in r["judges"]
                     if not j["refused"] and j["posterior"] is not None]
            sc = r.get("structural_confidence")
            if not posts or sc is None:
                tiers["none"] = tiers.get("none", 0) + 1
                continue
            # tier-ladder unanimity gate, candidate posterior bar
            emit = sc >= 0.90 and (r["probability"] is not None and
                    (r["probability"] >= bar or r["probability"] <= 1 - bar))
            tier, _ = escalation.route(posts, sc, emit)
            tiers[tier] = tiers.get(tier, 0) + 1
            if emit and r["probability"] is not None:
                emitted.append((r["probability"], r["label"]))
        m = acc_brier(emitted)
        auto_acc = None
        out["%.2f" % bar] = {**m, "emit_rate":
                             len(emitted) / len(rows) if rows else 0,
                             "tiers": tiers}
    escalation.AUTO_BAR = 0.85  # restore production default in-process
    # winner: min Brier; tie-break: higher emit rate at accuracy>=0.90
    cands = [(k, v) for k, v in out.items()
             if (v["accuracy"] or 0) >= 0.90]
    cands = cands or list(out.items())
    win = min(cands, key=lambda kv: (kv[1]["brier"] if kv[1]["brier"] is not None else 9,
                                    -(kv[1]["emit_rate"])))
    return {"table": out, "winner": win[0],
            "rationale": "min Brier on tier-ladder-routed verdicts (N=%d rows); "
                         "tie-break: higher emission rate at accuracy>=0.90; "
                         "tunes the tier ladder, not the abstention gate" % len(rows)}


def t2_margin(rows, esc):
    import escalation
    # labels: did/would debate change the outcome (correctness flip)?
    labels = {}
    for x in esc["part1_debate_escalated"]["items"]:
        labels[x["eval_id"]] = bool(x.get("correct_flip"))
    for x in esc["part2_counterfactual"]["items"]:
        if x.get("correct_flip") is not None:
            labels[x["eval_id"]] = bool(x["correct_flip"])
    lab_rows = [r for r in rows if r["eval_id"] in labels]
    out = {}
    for margin in (0.15, 0.25, 0.35):
        escalation.DISAGREE_MARGIN = margin
        escalation.AUTO_BAR = 0.85
        tp = fp = fn = tn = 0
        for r in lab_rows:
            posts = [j["posterior"] for j in r["judges"]
                     if not j["refused"] and j["posterior"] is not None]
            sc = r.get("structural_confidence") or 0.5
            tier, _ = escalation.route(posts, sc, True)
            fired = (tier == "DEBATE")
            y = labels[r["eval_id"]]
            if fired and y:
                tp += 1
            elif fired:
                fp += 1
            elif y:
                fn += 1
            else:
                tn += 1
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)
              if prec and rec and (prec + rec) else None)
        out["%.2f" % margin] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                                "precision": prec, "recall": rec, "f1": f1}
    escalation.DISAGREE_MARGIN = 0.25
    win = max(out.items(), key=lambda kv: (kv[1]["f1"] is not None, kv[1]["f1"] or -1))
    return {"table": out, "winner": win[0], "n_labeled": len(lab_rows),
            "rationale": "max F1 of the disagreement trigger as a "
                         "classifier for 'debate changes the outcome' "
                         "(labels from E3 counterfactuals, N=%d)" % len(lab_rows)}


def t3_panel_size(question_rows, concurrency):
    import oracle_ask
    rng = random.Random(20260920)
    # Scorable rows (bearing a probability); status is not required since
    # we rerun the panel -- cold-gate withholding does not block the test.
    sub = [q for q in question_rows if q.get("probability") is not None][:]
    rng.shuffle(sub)
    sub = sub[:20]
    cfgs = {"2": ["oracle-judge-a", "oracle-judge-b"],
            "3": ["oracle-judge-a", "oracle-judge-b", "oracle-judge-c"],
            "4": ["oracle-judge-a", "oracle-judge-b", "oracle-judge-c",
                  "oracle-judge-local"]}
    out = {}
    for name, models in cfgs.items():
        work = ("/home/toxic/estate/ranch/squawk/oracle/"
                "work-tune-panel%s-%d" % (name, int(time.time())))
        os.makedirs(work, exist_ok=True)
        os.environ["ORACLE_WORK"] = work

        def one(q):
            time.sleep(rng.uniform(0, 1.0))
            try:
                v = oracle_ask.run_ask(q["question"], models=models,
                                       timeout_s=90, budget_s=240)
            except Exception:
                return None
            if v.get("status") != "verdict" or v.get("probability") is None:
                return None
            return (v["probability"], q["label"], v.get("latency_s"),
                    v.get("llm_calls"), v.get("tier"))

        t0 = time.time()
        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            got = [f.result() for f in
                   cf.as_completed([ex.submit(one, q) for q in sub])]
        got = [g for g in got if g]
        m = acc_brier([(p, y) for p, y, _, _, _ in got])
        out[name] = {**m, "wall_s": round(time.time() - t0, 1),
                     "mean_latency_s": mean([g[2] for g in got]),
                     "mean_calls": mean([g[3] for g in got]),
                     "tiers": {t: sum(1 for g in got if g[4] == t)
                               for t in set(g[4] for g in got)}}
        print("  panel=%s n=%d acc=%.3f brier=%.4f" %
              (name, m["n"], m["accuracy"] or 0, m["brier"] or 0), flush=True)
    win = min(out.items(), key=lambda kv: kv[1]["brier"]
              if kv[1]["brier"] is not None else 9)
    return {"table": out, "winner": win[0], "n_questions": len(sub),
            "rationale": "min Brier on live rerun (N=%d questions, identical "
                         "conditions across panel sizes)" % len(sub)}


def t4_calibration_choice(rows):
    import calibration as cal
    per_judge = {}
    for r in rows:
        for j in r["judges"]:
            if not j["refused"] and j["posterior"] is not None:
                per_judge.setdefault(j["slot"], []).append(
                    (j["posterior"], r["label"]))
    out = {}
    for alias, items in per_judge.items():
        ps = [p for p, _ in items]
        ys = [y for _, y in items]
        if len(ps) < 10:
            out[alias] = {"n": len(ps), "skipped": "n<10"}
            continue
        res = {"n": len(ps)}
        for name, fit, pred in (
                ("raw", None, None),
                ("platt", cal.platt_fit, cal.platt_predict),
                ("isotonic", cal.isotonic_fit, cal.isotonic_predict)):
            if name == "raw":
                cp = ps
            else:
                cp = cal.cross_fitted_predict(fit, pred, ps, ys, k=5)
            nll = cal.nll(cp, ys)
            br = cal.brier(cp, ys)
            res[name] = {"nll": nll, "brier": br}
        res["dNLL_platt_vs_raw"] = res["platt"]["nll"] - res["raw"]["nll"]
        res["dNLL_iso_vs_raw"] = res["isotonic"]["nll"] - res["raw"]["nll"]
        res["winner"] = min(("raw", "platt", "isotonic"),
                            key=lambda k: res[k]["nll"])
        out[alias] = res
    winners = [v["winner"] for v in out.values()
               if "winner" in v]
    overall = max(set(winners), key=winners.count) if winners else None
    return {"per_judge": out, "overall_winner": overall,
            "rationale": "min 5-fold cross-fitted NLL per judge on eval "
                         "posteriors (N=%d questions)" %
                         len(rows)}


def t5_abstention(rows):
    import calibration as cal
    emitted = [r for r in rows if r["status"] == "verdict"
               and r["probability"] is not None]
    correct = {r["eval_id"]: ((r["probability"] >= 0.5) == bool(r["label"]))
               for r in emitted}
    out = {}
    for alpha in (0.01, 0.05, 0.10):
        for min_acc in (0.75, 0.80, 0.85):
            em, em_correct = 0, 0
            for r in emitted:
                hist = [correct[i] for i in correct if i != r["eval_id"]]
                # no label-count floor: the exact-binomial bound
                # withholds honestly at small n by itself
                k = sum(1 for h in hist if h)
                lo, _ = cal.clopper_pearson(k, len(hist), alpha)
                if lo >= min_acc:
                    em += 1
                    em_correct += 1 if correct[r["eval_id"]] else 0
            key = "a=%.2f/m=%.2f" % (alpha, min_acc)
            out[key] = {"emit_rate": em / len(emitted) if emitted else 0,
                        "emitted_accuracy":
                            em_correct / em if em else None,
                        "n_emitted": em}
    cands = [(k, v) for k, v in out.items()
             if (v["emitted_accuracy"] or 0) >= 0.90]
    cands = cands or list(out.items())
    win = max(cands, key=lambda kv: kv[1]["emit_rate"])
    return {"table": out, "winner": win[0],
            "rationale": "max emission rate subject to emitted accuracy "
                         ">= 0.90, warm-gate replay with leave-one-out "
                         "histories (N=%d emitted)" % len(emitted),
            "note": "mirrors engine.abstention_gate exactly (CP lower bound "
                    "on genuine-label history; no warm/cold branches, no "
                    "label-count floor)"}


def t6_debate_budget(rows, concurrency):
    import framing, engine, escalation, oracle_ask
    # Policy-DEBATE rows (disagreement-routed, gate_ok=True): the questions
    # where production would actually pay for a debate. status is not
    # required -- the debate runs on the question text.
    drows = [r for r in rows if r.get("policy_tier") == "DEBATE"
             and r["n_live"] >= 2][:12]
    cfgs = [(1, 2), (1, 3), (2, 2), (2, 3)]

    def run_cfg(r, k, rounds):
        framed = framing.frame_question(r["question"])
        if framed.get("status") == "refused":
            return None

        def _chat(model, prompt, t):
            res = oracle_ask.herd_chat(model, prompt, t, max_tokens=400)
            return {"content": res.get("text") or ""}

        d = escalation.debate_tier(
            framed["binary_question"], framed["resolution_criteria"], "",
            judges=["oracle-judge-a", "oracle-judge-b", "oracle-judge-c"],
            chat_fn=_chat, k=k, max_rounds=rounds,
            eps=escalation.DEBATE_EPS, per_advocate_timeout_s=90)
        adv = [engine.JudgePosterior(judge_id=a["model"],
                                     posterior=a["posterior"], cal_weight=0.5)
               for a in d["advocate_finals"]]
        final = engine.build_verdict(framed, adv)
        return {"p": final.get("probability"),
                "requests": d.get("requests", 0), "rounds": d["rounds"]}

    results = {}
    for k, rounds in cfgs:
        def one(r):
            try:
                return run_cfg(r, k, rounds)
            except Exception:
                return None
        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(one, r): r for r in drows}
            ok = []
            for f in cf.as_completed(futs):
                r = futs[f]
                g = f.result()
                if g and g["p"] is not None:
                    ok.append((r, g))
        results["k=%d/r=%d" % (k, rounds)] = {
            "n": len(ok), "mean_requests": mean([g["requests"] for _, g in ok]),
            "ps": [g["p"] for _, g in ok],
            "ids": [r["eval_id"] for r, _ in ok]}
        print("  k=%d r=%d n=%d req=%.1f" %
              (k, rounds, len(ok),
               mean([g["requests"] for _, g in ok]) or 0), flush=True)
    ref = results.get("k=2/r=3", {}).get("ps", [])
    ref_ids = results.get("k=2/r=3", {}).get("ids", [])
    table = {}
    for name, res in results.items():
        # align with reference by eval_id
        pairs = [(p, rp) for p, i, rp, ri in
                 zip(res["ps"], res["ids"], ref, ref_ids) if i == ri]
        dp = mean([abs(p - rp) for p, rp in pairs]) if pairs else None
        table[name] = {"n": res["n"], "mean_requests": res["mean_requests"],
                       "mean_abs_dp_vs_ref": dp}
    cands = [(k, v) for k, v in table.items()
             if (v["mean_abs_dp_vs_ref"] or 99) < 0.03]
    cands = cands or list(table.items())
    win = min(cands, key=lambda kv: kv[1]["mean_requests"] or 1e9)
    return {"table": table, "winner": win[0], "reference": "k=2/r=3",
            "n_questions": len(drows),
            "rationale": "cheapest (k, rounds) with mean|dp| < 0.03 vs the "
                         "(2,3) reference rerun (N=%d debate questions); "
                         "evidence text empty, same as E3" % len(drows)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--escalation", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    ts = int(time.time())
    work = "/home/toxic/estate/ranch/squawk/oracle/work-tune-%d" % ts
    os.makedirs(work, exist_ok=True)
    os.environ["ORACLE_WORK"] = work
    sys.path.insert(0, BIN)

    with open(a.rows) as f:
        rows = [json.loads(l) for l in f if l.strip()]

    out = {"ts": ts, "rows_path": a.rows, "oracle_work": work,
           "T1_unanimity_bar": t1_unanimity_bar(rows)}
    print("T1 winner:", out["T1_unanimity_bar"]["winner"], flush=True)
    if a.escalation:
        with open(a.escalation) as f:
            esc = json.load(f)
        out["T2_escalation_margin"] = t2_margin(rows, esc)
        print("T2 winner:", out["T2_escalation_margin"]["winner"], flush=True)
    out["T4_calibration_choice"] = t4_calibration_choice(rows)
    print("T4 winner:", out["T4_calibration_choice"]["overall_winner"],
          flush=True)
    out["T5_abstention"] = t5_abstention(rows)
    print("T5 winner:", out["T5_abstention"]["winner"], flush=True)
    if a.live:
        out["T3_panel_size"] = t3_panel_size(rows, a.concurrency)
        print("T3 winner:", out["T3_panel_size"]["winner"], flush=True)
        out["T6_debate_budget"] = t6_debate_budget(rows, a.concurrency)
        print("T6 winner:", out["T6_debate_budget"]["winner"], flush=True)
    path = os.path.join(RESULTS, "tuning_%d.json" % ts)
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("wrote %s" % path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
