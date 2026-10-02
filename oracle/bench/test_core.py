#!/usr/bin/env python3
"""Deterministic unit tests for the Oracle core. No model calls, no network.

Run: python3 bench/test_core.py
Covers: bayes guards, calibration math, engine pooling/gates,
evidence partitioning, escalation routing, sizing invariants.
"""
import math
import os
import sys

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
sys.path.insert(0, BIN)
os.environ.setdefault("ORACLE_WORK", "/tmp/oracle-test-work")

import bayes
import calibration as cal
import engine
import evidence as ev
import escalation
import sizing

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("FAIL %s %s" % (name, detail))


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---- bayes: Raven guards ----
check("llr clamp", bayes.clamp(5.0, -2.0, 2.0) == 2.0 and
      bayes.clamp(-5.0, -2.0, 2.0) == -2.0 and bayes.MAX_ABS_LLR == 2.0)
check("stance flip", bayes.effective_llr("supports_no", 1.5) == -1.5)
check("stance neutral", bayes.effective_llr("neutral", 1.5) == 0.0)
check("unverified soft clamp", bayes.clamp_unverified(1.9) == 0.2)
check("credibility cap medium", bayes.credibility_cap("medium", 1.9) == 0.8)
check("credibility cap high", bayes.credibility_cap("high", 1.9) == 1.9)
check("reflection clamp", bayes.clamp_reflection(2.0) == 1.0)
check("prob floor/ceil", bayes.PROB_FLOOR == 0.01 and bayes.PROB_CEIL == 0.99)
p, steps, pinned = bayes.apply_llrs(0.5, [2.0] * 6)
check("apply pins", pinned == "ceil" and p == 0.99, "p=%s pinned=%s" % (p, pinned))
check("logit roundtrip", approx(bayes.inv_logit(bayes.logit(0.3)), 0.3))
f = bayes.cluster_factors(["a", "a", "b"], [1.0, 1.0, 1.0], {"a": 2})
check("cluster discount", f[0] < 1.0 and f[1] < 1.0 and f[2] == 1.0, str(f))
check("confirmation ratio", approx(bayes.confirmation_ratio(0.6, [1.0, 1.0, -1.0]),
                                  2.0 / 3.0))
check("confirmation ratio none at 0.5",
      bayes.confirmation_ratio(0.5, [1.0]) is None)

# ---- calibration math ----
lo, hi = cal.clopper_pearson(8, 8, 0.05)
check("CP 8/8 lower", approx(lo, 0.6306, 1e-3), "lo=%s" % lo)
check("CP 0/8 upper", cal.clopper_pearson(0, 8, 0.05)[1] < 0.4)
check("CP symmetric 4/8", approx(cal.clopper_pearson(4, 8, 0.05)[0],
                                 1 - cal.clopper_pearson(4, 8, 0.05)[1], 1e-9))
check("bias point", approx(cal.bias_corrected_point(0.8, 0.9, 0.9), 0.875))
bc_lo, bc_hi = cal.bias_corrected_ci(0.8, 0.9, 0.9, 50, 100, 100)
check("bias CI ordered", bc_lo <= 0.875 <= bc_hi, "%s %s" % (bc_lo, bc_hi))
check("norm_ppf", approx(cal.norm_ppf(0.5), 0.0, 1e-9))
check("norm roundtrip", approx(cal.norm_cdf(cal.norm_ppf(0.7)), 0.7, 1e-9))
check("nll sane", cal.nll([0.9, 0.1], [1, 0]) < cal.nll([0.5, 0.5], [1, 0]))
import tempfile as _tf
_tmpd = _tf.mkdtemp(prefix="tc-gate-")
cal.CAL_DIR = _tmpd
cal.HISTORY_PATH = _tmpd + "/accepted_history.jsonl"
cal.DATASHEET_PATH = _tmpd + "/judge_datasheets.json"
cal.CAL_STATE_PATH = _tmpd + "/calibration_state.json"
_g, _reason = engine.abstention_gate(0.99, 0.99)
_gop = engine.gate_operating_point()
check("gate strict: no labels withholds", _g == "escalate",
      "no labels must never emit silently: %s" % _reason)
check("gate withhold never writes synthetic rows",
      not os.path.exists(cal.HISTORY_PATH), "withhold is read-only")
budget = cal.label_budget(100, {"j1": 1.0, "j2": 4.0})
check("sqrt budget", budget["j2"] > budget["j1"] and
      abs(sum(budget.values()) - 100) < 1e-9, str(budget))

# ---- engine ----
jp = [engine.JudgePosterior("a", 0.7, provider="p1"), engine.JudgePosterior("b", 0.8, provider="p2")]
post, contrib = engine.pooled_posterior(0.5, jp)
check("pooled", approx(post, 0.9032, 1e-3), "post=%s" % post)
check("pooled contrib", len(contrib) == 2)
jp_col = [engine.JudgePosterior("a", 0.7, provider="p1"), engine.JudgePosterior("b", 0.8, provider="p1")]
postc, contribc = engine.pooled_posterior(0.5, jp_col)
check("provider collapse one unit", approx(postc, 0.7534, 1e-3) and abs(sum(c["weight"] for c in contribc) - 1.0) < 1e-9, "post=%s" % postc)
refused = [engine.JudgePosterior("a", 0.7, refused=True)]
post2, _ = engine.pooled_posterior(0.5, refused)
check("refused ignored", post2 == 0.5)
feats = engine.disagreement_features(jp)
check("struct conf range", 0.0 <= feats["confidence"] <= 1.0)
v = engine.build_verdict({"binary_question": "Q?", "base_rate_prior": 0.5,
                          "question_id": "t1", "resolution_criteria": "c"},
                         jp)
check("verdict shape", v["status"] in ("verdict", "escalate") and
      "verdict_sha256" in v and "gate" in v)
check("engine owns numbers", 0.01 <= v["probability"] <= 0.99)
flags = engine.check_canaries(jp, [{"id": "c1", "answer": True}])
jp[0].__dict__["canary_scores"] = {"c1": 0.02}  # confidently anti-answer
flags = engine.check_canaries(jp, [{"id": "c1", "answer": True}])
check("canary gaming flag", len(flags) == 1 and
      flags[0]["pattern"] == "confident_anti_answer", str(flags))

# ---- evidence ----
items = [{"id": str(i), "text": "e%d" % i, "relevance": 1.0 - i / 20.0,
          "source": "s"} for i in range(20)]
part = ev.partition_evidence(items, 4)
priv_ids = [e["id"] for grp in part["private"] for e in grp]
check("partition disjoint", len(set(priv_ids)) == len(priv_ids))
check("partition covers", len(priv_ids) + len(part["public"]) == 20)
c = ev.verify_claim_urls({"urls": ["u1"]}, ["u1", "u2"])
check("url verified", c["verified"])
c2 = ev.verify_claim_urls({"urls": ["u9"]}, ["u1", "u2"])
check("url fabrication", not c2["verified"])
post3, steps3, rep = ev.apply_claims(0.5, [
    {"text": "t1", "stance": "supports_yes", "llr": 5.0,
     "cluster_id": "x", "credibility": "low", "urls": ["u1"]}], None, ["u1"])
check("claim guards compose", steps3[0]["llr"] == 0.25 and
      "credibility_cap" in steps3[0]["guards"], str(steps3[0]))

# ---- escalation ----
tier, why = escalation.route([0.9, 0.92, 0.88], 0.95, True)
check("auto tier", tier == "AUTO", tier)
tier2, _ = escalation.route([0.9, 0.3, 0.6], 0.4, True)
check("debate tier", tier2 == "DEBATE", tier2)
tier3, _ = escalation.route([], 0.5, False)
check("human tier empty", tier3 == "HUMAN", tier3)
tier4, _ = escalation.route([0.7, 0.75], 0.7, True, invariant_ok=False)
check("invariant violation debates", tier4 == "DEBATE", tier4)
mock = lambda model, prompt, timeout_s: {"content": "0.6"}
d = escalation.debate_tier("Q?", "crit", "ev", ["oracle-judge-a"], mock,
                           k=2, max_rounds=2)
check("debate budgeted", d["rounds"] <= 2 and 0.01 <= d["posterior"] <= 0.99)

# ---- sizing ----
check("wang 0.5 ~ 0.57", approx(sizing.wang_fair_value(0.5), 0.5726, 1e-3))
check("kelly no edge", sizing.kelly_fraction(0.5, 0.5) == 0.0)
check("kelly edge", sizing.kelly_fraction(0.65, 0.57) > 0)
s = sizing.size_stake(0.65, 0.57, 1000)
check("size action", s["action"] == "bet_yes" and s["stake"] <= 100,
      str(s))
s2 = sizing.size_stake(0.55, 0.54, 1000)
check("size no bet", s2["action"] == "no_bet", str(s2))
viol = sizing.invariant_check([
    {"id": "a", "p": 0.6, "group": "g1", "group_kind": "exclusive"},
    {"id": "b", "p": 0.6, "group": "g1", "group_kind": "exclusive"}])
check("exclusivity violation", len(viol) == 1 and
      viol[0]["invariant"] == "exclusivity")
viol2 = sizing.invariant_check([
    {"id": "a", "p": 0.8, "implies": "b"},
    {"id": "b", "p": 0.5}])
check("implication violation", len(viol2) == 1)

#!/usr/bin/env python3
"""Rebuilt hardening test sections for bench/test_core.py (appended before the
final print). Deterministic: no model calls, no network."""
import threading
import time

import framing
import oracle_ask


#!/usr/bin/env python3
"""Rebuilt hardening test sections for bench/test_core.py (appended before the
final print). Deterministic: no model calls, no network."""
import threading
import time

import framing
import oracle_ask


#!/usr/bin/env python3
"""Rebuilt hardening test sections for bench/test_core.py (appended before the
final print). Deterministic: no model calls, no network."""
import threading
import time

import framing
import oracle_ask


#!/usr/bin/env python3
"""Rebuilt hardening test sections for bench/test_core.py (appended before the
final print). Deterministic: no model calls, no network."""
import threading
import time

import framing
import oracle_ask

# ---- framing: fail-closed question intake ----
_framing_cases = [
    ("Will this work?", "refused"),
    ("the market is really big these days", "refused"),
    ("hello", "refused"),
    ("Will Bitcoin go up?", "refused"),
    ("Will Bitcoin go up by Friday?", "refused"),
    ("Will the herd router serve 100 or more models by 2026-12-31?", "framed"),
    ("Will the sun rise tomorrow?", "framed"),
    ("Did Apollo 11 land humans on the Moon in 1969?", "framed"),
    ("Is 2 + 2 equal to 5 in standard arithmetic?", "framed"),
    ("Was the Eiffel Tower completed before the year 1900?", "framed"),
    ("Will Bitcoin exceed $100,000 by December 31, 2026?", "framed"),
]
for _q, _want in _framing_cases:
    _r = framing.frame_question(_q)
    check("framing %s -> %s" % (_q[:44], _want),
          _r["status"] == _want, str(_r.get("refusal_reason")))
_f5 = framing.frame_question(
    "Will the herd router serve 100 or more models by 2026-12-31?")
check("framing accepts real question",
      _f5["status"] == "framed" and _f5["question_id"]
      and _f5["base_rate_prior"] == 0.5, str(_f5))
_btc = framing.frame_question("Will Bitcoin go up?")
check("bitcoin refusal names missing pieces",
      "resolution date" in _btc.get("refusal_reason", "")
      and "resolvable event" in _btc.get("refusal_reason", ""),
      str(_btc))
check("bitcoin refusal carries clarification",
      bool(_btc.get("clarification_request")), str(_btc))

# ---- router/model separation: aliases only ----
_rejected = False
try:
    oracle_ask._check_alias_models(
        ["openrouter-free/nex-agi/nex-n2.5-mini:free"])
except SystemExit:
    _rejected = True
check("concrete model rejected", _rejected)
try:
    oracle_ask._check_alias_models(
        list(oracle_ask.DEFAULT_JUDGES) + [oracle_ask.FALLBACK_JUDGE])
    _aliases_ok = True
except SystemExit:
    _aliases_ok = False
check("alias panel accepted", _aliases_ok)
check("default judges are aliases",
      all("/" not in m and ":" not in m for m in oracle_ask.DEFAULT_JUDGES),
      str(oracle_ask.DEFAULT_JUDGES))
check("fallback is local alias",
      oracle_ask.FALLBACK_JUDGE == "oracle-judge-local",
      oracle_ask.FALLBACK_JUDGE)

# ---- calibration ownership: engine applies exactly once per posterior ----
_apply_calls = []
_orig_apply = cal.CalibrationLoop.apply


def _counting_apply(self, judge_id, score):
    _apply_calls.append((judge_id, score))
    return _orig_apply(self, judge_id, score)


cal.CalibrationLoop.apply = _counting_apply
try:
    _fj = [engine.JudgePosterior("oracle-judge-a", 0.72),
           engine.JudgePosterior("oracle-judge-b", 0.68),
           engine.JudgePosterior("oracle-judge-c", 0.75)]
    _apply_calls.clear()
    _v1 = engine.build_verdict(_f5, _fj)
    check("engine applies calibration exactly once per judge posterior",
          len(_apply_calls) == len(_fj)
          and sorted(j for j, _ in _apply_calls)
          == sorted(j.judge_id for j in _fj),
          "apply() calls=%d for %d judges: %s"
          % (len(_apply_calls), len(_fj), _apply_calls))
    _v2 = engine.build_verdict(_f5, _fj)
    check("re-running build_verdict re-applies once more, never double-applies",
          len(_apply_calls) == 2 * len(_fj),
          "apply() calls after 2 runs=%d" % len(_apply_calls))
finally:
    cal.CalibrationLoop.apply = _orig_apply

check("engine aggregation deterministic",
      _v1["probability"] == _v2["probability"]
      and _v1["verdict_sha256"] == _v2["verdict_sha256"],
      "%s %s" % (_v1["probability"], _v2["probability"]))

# ask path never touches calibration
_ask_src = open(os.path.join(BIN, "oracle_ask.py")).read()
check("ask path never applies calibration",
      "CalibrationLoop" not in _ask_src and "loop.apply" not in _ask_src,
      "calibration must live in engine.build_verdict only")

# ---- resilient judge: bounded retry then local fallback ----
class _FakeJP(object):
    def __init__(self, refused, posterior=0.7, judge_id="x"):
        self.refused = refused
        self.posterior = posterior
        self.judge_id = judge_id


def _judge_seq(results):
    calls = []

    def fn(model, prompt, timeout_s):
        calls.append((model, timeout_s))
        r = results[min(len(calls) - 1, len(results) - 1)]
        return _FakeJP(r[0], r[1], model)
    fn.calls = calls
    return fn


_seq = _judge_seq([(False, 0.8)])
jp, info, _att = oracle_ask._resilient_judge("oracle-judge-a", "Q?", 90,
                                       judge_fn=_seq)
check("resilient live slot",
      not jp.refused and info["served_by"] == "oracle-judge-a"
      and info["attempts"] == 1 and len(_seq.calls) == 1, str(info))

_seq = _judge_seq([(True, 0.5), (False, 0.6)])
jp, info, _att = oracle_ask._resilient_judge("oracle-judge-a", "Q?", 90,
                                       judge_fn=_seq)
check("resilient retry recovers",
      not jp.refused and info["served_by"] == "oracle-judge-a"
      and info["attempts"] == 2 and len(_seq.calls) == 2, str(info))

_seq = _judge_seq([(True, 0.5), (True, 0.5), (False, 0.55)])
jp, info, _att = oracle_ask._resilient_judge("oracle-judge-a", "Q?", 90,
                                       judge_fn=_seq)
check("resilient falls back to local",
      not jp.refused and info["served_by"] == oracle_ask.FALLBACK_JUDGE
      and info["attempts"] == 3
      and [c[0] for c in _seq.calls] ==
      ["oracle-judge-a", "oracle-judge-a", oracle_ask.FALLBACK_JUDGE],
      "%s %s" % (info, _seq.calls))

_seq = _judge_seq([(True, 0.5)] * 5)
jp, info, _att = oracle_ask._resilient_judge("oracle-judge-a", "Q?", 90,
                                       judge_fn=_seq)
check("resilient bounded fail-open",
      jp.refused and info["refused"] and info["attempts"] == 3
      and len(_seq.calls) == 3, str(info))

# ---- debate: parallel, diverse, bounded, fail-open ----
_active = 0
_peak = 0
_plock = threading.Lock()


def _par_chat(model, prompt, timeout_s):
    global _active, _peak
    with _plock:
        _active += 1
        _peak = max(_peak, _active)
    try:
        time.sleep(0.05)
        return {"content": '{"posterior": 0.7}'}
    finally:
        with _plock:
            _active -= 1


_judges = ["oracle-judge-a", "oracle-judge-b", "oracle-judge-c"]
_d = escalation.debate_tier("Will X happen by 2027?", "crit", "ev", _judges,
                            _par_chat, k=2, max_rounds=2)
check("debate parallel", _peak > 1, "peak=%d" % _peak)
check("debate budgeted",
      _d["rounds"] <= 2 and 0.01 <= _d["posterior"] <= 0.99, str(_d))
check("debate finals shape",
      len(_d["advocate_finals"]) == 4 and all(
          set(f) >= {"model", "side", "posterior", "rounds"}
          for f in _d["advocate_finals"]),
      str(_d["advocate_finals"]))
_yes_models = [f["model"] for f in _d["advocate_finals"] if f["side"] == "YES"]
_no_models = [f["model"] for f in _d["advocate_finals"] if f["side"] == "NO"]
check("debate same-side diversity",
      len(set(_yes_models)) == 2 and len(set(_no_models)) == 2,
      "%s %s" % (_yes_models, _no_models))
check("debate counts requests",
      _d["requests"] == _d["rounds"] * len(_d["advocate_finals"]),
      str(_d["requests"]))


def _flaky_chat(model, prompt, timeout_s):
    if model == "oracle-judge-a":
        raise ConnectionError("free-tier flake")
    return {"content": "0.62"}


_d2 = escalation.debate_tier("Will X happen by 2027?", "crit", "ev",
                             ["oracle-judge-a", "oracle-judge-b"],
                             _flaky_chat, k=1, max_rounds=1)
_f0 = _d2["advocate_finals"][0]
check("debate bounded retry switches alias",
      _f0["model"] == "oracle-judge-b"
      and 0.01 <= _f0["posterior"] <= 0.99,
      str(_f0))
check("debate retry counted",
      _d2["requests"] == 3,  # 2 advocates + 1 bounded retry
      str(_d2["requests"]))


def _dead_chat(model, prompt, timeout_s):
    raise ConnectionError("all down")


_d3 = escalation.debate_tier("Will X happen by 2027?", "crit", "ev",
                             ["oracle-judge-a", "oracle-judge-b"],
                             _dead_chat, k=1, max_rounds=1)
check("debate fail-open on priors",
      all(abs(f["posterior"] - (0.85 if f["side"] == "YES" else 0.15)) < 0.03
          for f in _d3["advocate_finals"]),
      str(_d3["advocate_finals"]))

# debate finals re-enter the engine: gates, hash, contributions recomputed
_adv_judges = [engine.JudgePosterior(judge_id=a["model"],
                                     posterior=a["posterior"],
                                     cal_weight=0.5)
               for a in _d["advocate_finals"]]
_dv = engine.build_verdict(_f5, _adv_judges)
check("debate final rebuilt by engine",
      _dv["status"] in ("verdict", "escalate")
      and _dv["verdict_sha256"] and len(_dv["judge_contributions"]) == 4,
      "%s %s" % (_dv["status"], _dv["verdict_sha256"]))

# ---- canonical verdict hash: recompute and match the ledger row ----
import hashlib as _hl
import json as _json
_hv = engine.build_verdict({"binary_question": "Q?", "base_rate_prior": 0.5,
                            "question_id": "hash1",
                            "resolution_criteria": "c"},
                           [engine.JudgePosterior("a", 0.7),
                            engine.JudgePosterior("b", 0.8)])
_canon = _json.dumps(
    {k: _hv[k] for k in
     ("question_id", "probability", "judge_contributions")},
    sort_keys=True)
_expected = _hl.sha256(_canon.encode()).hexdigest()[:16]
check("verdict hash recomputes exactly",
      _hv["verdict_sha256"] == _expected,
      "%s vs %s" % (_hv["verdict_sha256"], _expected))
_lp = "/home/toxic/.xfer/oracle-test-work/hash_ledger.jsonl"
engine.record_verdict(_hv, path=_lp)
_row = _json.loads(open(_lp).read().strip().split("\n")[-1])
check("ledger row preserves hash",
      _row["verdict_sha256"] == _expected == _hv["verdict_sha256"],
      str(_row.get("verdict_sha256")))

# ---- none-content robustness: free-tier nulls never crash ----
_orig_herd = oracle_ask.herd_chat
oracle_ask.herd_chat = (
    lambda model, prompt, timeout_s=90, max_tokens=1500:
    {"ok": True, "text": None, "latency_s": 0.1})
try:
    _njp, _natt = oracle_ask.judge_once("oracle-judge-a", "Q?", 30)
finally:
    oracle_ask.herd_chat = _orig_herd
check("judge_once null content -> parse_failure not crash",
      not _njp.refused and not _njp.valid
      and _njp.failure_category == engine.FAILURE_PARSE
      and _njp.posterior == 0.5,
      "%s %s %s" % (_njp.refused, _njp.valid, _njp.failure_category))

_ok_ar = escalation._advocate_round(
    lambda m, p, t: {"content": None}, "oracle-judge-a", "Q?", 0.7, 30)
check("advocate_round null content -> ok=False not raise",
      _ok_ar == (0.7, "oracle-judge-a", False), str(_ok_ar))

_ok_ar2 = escalation._advocate_round(
    lambda m, p, t: {"content": "garbage no number"},
    "oracle-judge-a", "Q?", 0.7, 30)
check("advocate_round unparseable -> prior nudge ok=True",
      _ok_ar2[2] is True and abs(_ok_ar2[0] - 0.72) < 1e-9, str(_ok_ar2))

# ---- budget exhaustion: verdict, never a crash ----
def _slow_slot(model, prompt, timeout_s):
    time.sleep(2.0)
    jp = engine.JudgePosterior(judge_id=model, posterior=0.5, refused=True)
    return jp, {"slot": model, "served_by": model, "refused": True,
                "attempts": 0}, []


_orig_rj = oracle_ask._resilient_judge
oracle_ask._resilient_judge = _slow_slot
try:
    _t0 = time.time()
    _bv = oracle_ask.run_ask(
        "Will the herd router serve 100 or more models by 2026-12-31?",
        models=["oracle-judge-a"], timeout_s=5, allow_debate=False, budget_s=1)
    _dt = time.time() - _t0
finally:
    oracle_ask._resilient_judge = _orig_rj
check("budget exhaustion yields verdict not crash",
      _bv["status"] in ("verdict", "escalate") and _dt < 30,
      "%s %.1fs" % (_bv["status"], _dt))
check("exhausted slot recorded executor_error",
      _bv["judge_slots"] and not _bv["judge_slots"][0]["valid"]
      and _bv["judge_slots"][0]["failure_category"] == "executor_error",
      str(_bv.get("judge_slots")))

print("PASS %d FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
