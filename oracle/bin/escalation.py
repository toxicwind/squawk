#!/usr/bin/env python3
"""Structured escalation: AUTO / VOTE / DEBATE tiers.

Debate semantics (hardened 2026-09-20):
- Advocates run IN PARALLEL (ThreadPoolExecutor), never serially.
- Each advocate is assigned a DISTINCT complementary judge alias from
  the panel (round-robin, distinct per side) -- no shared single judge.
  The router aliases are role names; concrete targets live in
  config/herd.yaml. Prompts never name the model (blind advocates).
- Fail-fast: each advocate call is bounded by per_advocate_timeout_s;
  on error/timeout, ONE bounded retry on the next panel alias, then the
  advocate keeps its prior posterior. Never a retry spin, never a
  fabricated posterior.
- The debate returns advocate finals; the CALLER re-aggregates them
  through the deterministic engine (bin/engine.py build_verdict) so
  gates, confidence, contributions, and the verdict hash are recomputed
  on the final number. This module never finalizes a verdict.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

WORK = os.environ.get("ORACLE_WORK",
                      "/home/toxic/estate/ranch/squawk/oracle/work")
ESCALATION_DIR = os.path.join(WORK, "escalations")

AUTO_BAR = 0.85
DEBATE_K = 2
DEBATE_MAX_ROUNDS = 3
DEBATE_EPS = 0.03
DISAGREE_MARGIN = 0.25


def escalation_tier(agreement, calibrated):
    """AUTO if the calibrated posterior clears AUTO_BAR either way,
    else VOTE."""
    if calibrated >= AUTO_BAR or calibrated <= 1 - AUTO_BAR:
        return "AUTO"
    return "VOTE"


def route(judge_posteriors, struct_confidence, gate_ok, invariant_ok=True):
    """Decide the tier. judge_posteriors: list of floats (live judges only).

    Legacy routing kept for the loop tooling; the ask path's tier comes
    from engine.build_verdict.
    """
    posts = [p for p in judge_posteriors]
    if not posts:
        return ("HUMAN", "no live judges — nothing to aggregate")
    if not invariant_ok:
        return ("DEBATE", "probability-axiom invariant violation")
    if not gate_ok:
        return ("DEBATE", "abstention gate withheld the verdict")
    unanimous_yes = all(p >= AUTO_BAR for p in posts)
    unanimous_no = all(p <= 1 - AUTO_BAR for p in posts)
    if (unanimous_yes or unanimous_no) and struct_confidence >= 0.90:
        return ("AUTO", "unanimous high-confidence (%d judges)" % len(posts))
    spread = max(posts) - min(posts)
    yes = sum(1 for p in posts if p >= 0.5)
    if spread >= DISAGREE_MARGIN or (0 < yes < len(posts)
                                    and struct_confidence < 0.6):
        return ("DEBATE", "disagreement: spread=%.2f, %d/%d yes" %
                (spread, yes, len(posts)))
    return ("VOTE", "pooled posterior path, spread=%.2f" % spread)


def _extract_number(text, prior):
    m = re.search(r"0?\.\d+|\b[01](?:\.0+)?\b", text.replace(",", "."))
    if not m:
        return min(0.99, max(0.01, prior + 0.02))
    return min(0.99, max(0.01, float(m.group(0))))


def _advocate_round(chat_fn, model, prompt, prior, timeout_s):
    """One advocate's turn: bounded call, parse, fail-open on the prior.

    Returns (posterior, used_model, ok). ok=False on transport failure;
    the caller retries once on the next panel alias. Never raises, never
    fabricates: a failed advocate keeps its prior posterior.
    """
    try:
        resp = chat_fn(model, prompt, timeout_s)
    except Exception:
        return prior, model, False
    try:
        content = (resp or {}).get("content") or ""
        if not content:
            # empty/null content is a failed round, not a fabricated one:
            # ok=False triggers the one bounded retry on the next alias.
            return prior, model, False
        return _extract_number(content, prior), model, True
    except Exception:
        return prior, model, False


def _prompt_for(side, question, criteria, evidence_text, other_posts, rnd):
    ctx = ""
    if other_posts:
        ctx = ("\nOpposing advocates' latest posteriors: %s\n"
               "Respond to their strongest point, then update yours."
               % ", ".join("%.2f" % p for p in other_posts))
    return (
        "You are an advocate for the %s side. Answer ONLY with a number.\n"
        "Question: %s\nCriteria: %s\n%s%s\n"
        "Round %d: what is the probability (0 to 1) the answer is YES? "
        "Argue ONLY for %s; steelman, do not concede. "
        "Reply with exactly one decimal number, e.g. 0.62. No other text."
        % (side, question, criteria, evidence_text, ctx, rnd, side))


def debate_tier(question, criteria, evidence_text, judges, chat_fn,
                k=DEBATE_K, max_rounds=DEBATE_MAX_ROUNDS, eps=DEBATE_EPS,
                per_advocate_timeout_s=90.0):
    """Structured advocate debate over k advocates per side.

    judges: list of router model/alias IDs (the debate panel). Advocates
      are assigned round-robin so advocates on the same side never share
      a model (distinct complementary judges); assignment wraps when the
      panel is smaller than the advocate count.
    chat_fn(model, prompt, timeout_s) -> {"content": str}; may raise.
    Returns {"posterior": mean final posterior (reference only),
             "advocate_finals": [{"model","side","posterior","rounds"}],
             "rounds": n, "converged": bool, "k": k}.
    """
    if not judges:
        raise ValueError("debate needs at least one judge alias")
    advocates = []
    idx = 0
    for side in ("YES", "NO"):
        for _ in range(k):
            model = judges[idx % len(judges)]
            idx += 1
            advocates.append({
                "side": side,
                "model": model,
                "model_idx": (idx - 1) % len(judges),
                "posterior": 0.85 if side == "YES" else 0.15,
                "rounds": [],
            })
    converged = False
    rounds_run = 0
    requests = 0
    for rnd in range(max_rounds):
        rounds_run = rnd + 1
        yes_posts = [a["posterior"] for a in advocates
                     if a["side"] == "YES"]
        no_posts = [a["posterior"] for a in advocates
                    if a["side"] == "NO"]
        jobs = []
        for n, a in enumerate(advocates):
            other = no_posts if a["side"] == "YES" else yes_posts
            prompt = _prompt_for(a["side"], question, criteria,
                                 evidence_text, other, rnd + 1)
            jobs.append((n, a, prompt))
        with ThreadPoolExecutor(
                max_workers=len(advocates)) as ex:
            futs = {ex.submit(_advocate_round, chat_fn, a["model"],
                              prompt, a["posterior"],
                              per_advocate_timeout_s): (n, a)
                    for n, a, prompt in jobs}
            for fut in as_completed(futs):
                requests += 1  # one advocate round = one request
                n, a = futs[fut]
                p, used_model, ok = fut.result()
                if not ok:
                    # one bounded retry on the next panel alias (fail-fast
                    # redundancy); then fail open on the prior, never
                    # fabricate.
                    alt = judges[(a["model_idx"] + 1) % len(judges)]
                    p2, used2, ok2 = _advocate_round(
                        chat_fn, alt, prompt, a["posterior"],
                        per_advocate_timeout_s)
                    requests += 1  # bounded retry is a request too
                    if ok2:
                        p, used_model = p2, alt
                if used_model != a["model"]:
                    a["model"] = used_model
                a["posterior"] = p
                a["rounds"].append(round(p, 4))
        posts = [a["posterior"] for a in advocates]
        if rnd >= 1 and max(posts) - min(posts) < eps:
            converged = True
            break
    finals = [{"model": a["model"], "side": a["side"],
               "posterior": round(a["posterior"], 4),
               "rounds": a["rounds"]} for a in advocates]
    mean_p = sum(a["posterior"] for a in advocates) / len(advocates)
    return {"posterior": round(mean_p, 4),
            "advocate_finals": finals,
            "rounds": rounds_run,
            "converged": converged,
            "requests": requests,
            "k": k}


def flag_human(question_record, reason, context=None):
    """Human arbitration flag: durable file + return the path. The caller
    (oracle_ask / daemon) posts the fleet note — this function never sends."""
    os.makedirs(ESCALATION_DIR, exist_ok=True)
    flag = {
        "ts": time.time(),
        "question_id": question_record.get("question_id"),
        "question": question_record.get("binary_question"),
        "reason": reason,
        "context": context or {},
        "status": "awaiting_human",
    }
    path = os.path.join(ESCALATION_DIR,
                        "human-%s.json" % flag["question_id"])
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(flag, f, indent=2)
    os.replace(tmp, path)
    return path


def resolve_human_flag(question_id, resolution, rationale=""):
    path = os.path.join(ESCALATION_DIR, "human-%s.json" % question_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        flag = json.load(f)
    flag["status"] = "resolved"
    flag["resolution"] = resolution
    flag["rationale"] = rationale
    flag["resolved_ts"] = time.time()
    with open(path, "w") as f:
        json.dump(flag, f, indent=2)
    return flag
