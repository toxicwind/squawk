#!/usr/bin/env python3
"""Regression tests for the oracle-market reliability + calibration redesign.

Covers the defect surface found 2026-09-21 (collapsed error classes,
lost attempt evidence, provider-blind aggregation, provenance-blind
history, cold unanimity bypass, synthetic labels, 8-label discontinuity):

  transport:      HTTP status / error body preserved; timeout vs 5xx vs
                  429 vs connection classified, never as refusal
  judge path:     genuine refusal != parse failure != schema failure;
                  all retry/fallback attempts preserved with correlation id
  provider:       same-provider aliases collapse to one vote unit;
                  correlated provider outage attributed to the provider
  calibration:    only genuinely labeled rows (explicit label_source)
                  count; legacy rows quarantined; no synthetic labels;
                  prior shrinkage reported explicitly
  gate:           finite-sample withholding at n=0 (no unanimity bypass);
                  gate reads only, never writes; operating point exposes
                  the safety-vs-served-traffic numbers

Run:  python3 bin/test_oracle_reliability.py
Exit 0 = all pass, 1 = failures.
"""
import json
import os
import shutil
import sys
import tempfile

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BIN)

import engine
import calibration as cal

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "oracle_ask_under_test", os.path.join(BIN, "oracle_ask.py"))
_oa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_oa)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("ok   %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILURES.append(name)


# ---------------------------------------------------------------- fixtures

def _mk_jp(judge_id, posterior=0.7, refused=False, valid=True,
           category=None, provider=None):
    return engine.JudgePosterior(
        judge_id=judge_id, posterior=posterior, refused=refused, valid=valid,
        failure_category=category, provider=provider)


def _mk_att(attempt_no=1, slot_alias="a", category=None,
            correlation_id="corr-test", provider="p1"):
    return engine.JudgeAttempt(attempt_no=attempt_no, slot_alias=slot_alias,
                               provider_requested=provider,
                               failure_category=category,
                               http_status=500,
                               correlation_id=correlation_id,
                               error_excerpt="boom")


def _slot(valid, category, provider, refused=False):
    return {"slot": "s", "valid": valid, "refused": refused,
            "attempts": [{"failure_category": category,
                          "provider_requested": provider,
                          "slot_alias": "s"}]}


def _stub_herd_chat(responses):
    """responses: list of dicts to return in order (last repeats)."""
    calls = {"n": 0}

    def stub(model, prompt, timeout_s=90, max_tokens=1500):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return dict(responses[i])
    return stub, calls


def _err_stub(error, error_kind, http_status, error_body):
    return {"ok": False, "error": error, "error_kind": error_kind,
            "http_status": http_status, "error_body": error_body,
            "latency_s": 1.0, "usage": {}, "text": None,
            "model_served": None, "provider_served": None,
            "refusal": None, "server": None}


def _ok_stub(text):
    return {"ok": True, "text": text, "latency_s": 0.9, "usage": {},
            "http_status": 200, "model_served": "p1/m1",
            "provider_served": "p1", "refusal": None, "server": "x",
            "error": None, "error_kind": None, "error_body": None}


# ---------------------------------------------------------------- transport

def test_http_5xx_preserved():
    stub, _ = _stub_herd_chat([_err_stub(
        "HTTPError 500: Internal Server Error", "http", 500,
        "engine meltdown, trace xyz")])
    _oa.herd_chat = stub
    jp, att = _oa.judge_once("a", "p", 5)
    check("http-5xx: not refusal", not jp.refused)
    check("http-5xx: not valid", not jp.valid and not jp.live)
    check("http-5xx: category",
          jp.failure_category == engine.FAILURE_HTTP_5XX,
          repr(jp.failure_category))
    check("http-5xx: status preserved", att.http_status == 500)
    check("http-5xx: body excerpt kept",
          att.error_excerpt and "meltdown" in att.error_excerpt,
          repr(att.error_excerpt))
    check("http-5xx: attempts recorded", att.attempt_no == 1)


def test_timeout_classified():
    stub, _ = _stub_herd_chat([_err_stub("URLError: timed out", "timeout",
                                         None, None)])
    _oa.herd_chat = stub
    jp, _ = _oa.judge_once("a", "p", 45)
    check("timeout: category", jp.failure_category == engine.FAILURE_TIMEOUT,
          repr(jp.failure_category))
    check("timeout: not refusal", not jp.refused and not jp.valid)


def test_connection_classified():
    stub, _ = _stub_herd_chat([_err_stub(
        "URLError: [Errno 111] Connection refused", "connection", None,
        None)])
    _oa.herd_chat = stub
    jp, _ = _oa.judge_once("a", "p", 45)
    check("connection: category",
          jp.failure_category == engine.FAILURE_CONN,
          repr(jp.failure_category))


def test_429_classified():
    stub, _ = _stub_herd_chat([_err_stub("HTTPError 429: Too Many Requests",
                                         "http", 429, "rate limit")])
    _oa.herd_chat = stub
    jp, _ = _oa.judge_once("a", "p", 5)
    check("429: category", jp.failure_category == engine.FAILURE_HTTP_429,
          repr(jp.failure_category))


def test_200_nonjson_is_parse_failure_not_refusal():
    stub, _ = _stub_herd_chat([_ok_stub("hello world, no json here")])
    _oa.herd_chat = stub
    jp, _ = _oa.judge_once("a", "p", 5)
    check("parse: category", jp.failure_category == engine.FAILURE_PARSE,
          repr(jp.failure_category))
    check("parse: not refusal", not jp.refused)
    check("parse: not valid", not jp.valid)
    check("parse: served model kept", jp.model_family == "p1")


def test_schema_failure_missing_posterior():
    stub, _ = _stub_herd_chat(
        [_ok_stub('{"claims": [], "reasoning_summary": "x"}')])
    _oa.herd_chat = stub
    jp, _ = _oa.judge_once("a", "p", 5)
    check("schema: missing posterior -> schema_failure",
          jp.failure_category == engine.FAILURE_SCHEMA and not jp.valid
          and not jp.refused, repr(jp.failure_category))


def test_schema_failure_nan_posterior():
    stub, _ = _stub_herd_chat([_ok_stub('{"posterior": NaN}')])
    _oa.herd_chat = stub
    jp, _ = _oa.judge_once("a", "p", 5)
    # NaN is not valid JSON for json.loads -> parse_failure is also honest;
    # either way it must not be a refusal and must not be valid.
    check("nan: not valid, not refusal",
          not jp.valid and not jp.refused, repr(jp.failure_category))


def test_genuine_refusal():
    stub, _ = _stub_herd_chat([_ok_stub("I can't answer that, sorry.")])
    _oa.herd_chat = stub
    jp, att = _oa.judge_once("a", "p", 5)
    check("refusal: refused", jp.refused and not jp.valid and not jp.live)
    check("refusal: category",
          jp.failure_category == engine.FAILURE_REFUSAL,
          repr(jp.failure_category))
    check("refusal: attempt category",
          att.failure_category == engine.FAILURE_REFUSAL)


def test_ok_judge():
    stub, _ = _stub_herd_chat([_ok_stub(
        '{"posterior": 0.7, "verbal_confidence": "medium", '
        '"claims": [{"text": "c1", "stance": "supports_yes", '
        '"llr": 0.5, "cluster_id": "k", "rationale": "r", '
        '"urls": [], "credibility": "medium"}], '
        '"reasoning_summary": "rs"}')])
    _oa.herd_chat = stub
    jp, att = _oa.judge_once("a", "p", 5, attempt_no=2,
                             provider_requested="p1",
                             correlation_id="corr-1")
    check("ok: live", jp.live and jp.valid)
    check("ok: posterior", abs(jp.posterior - 0.7) < 1e-9)
    check("ok: provider", jp.provider == "p1")
    check("ok: attempt no + corr id",
          att.attempt_no == 2 and att.correlation_id == "corr-1")
    check("ok: category", att.failure_category == engine.FAILURE_OK)


# ------------------------------------------------------- resilient judge

def _diverse_stub(seen, ok_on=("c",), fail_cat=engine.FAILURE_HTTP_5XX):
    def fn(alias, prompt, t, attempt_no=1, provider_requested=None,
           correlation_id=None):
        seen.append(alias)
        if alias in ok_on:
            return (_mk_jp(alias, posterior=0.8,
                           provider=provider_requested),
                    _mk_att(attempt_no=attempt_no, slot_alias=alias,
                            category=engine.FAILURE_OK,
                            correlation_id=correlation_id))
        return (_mk_jp(alias, valid=False, category=fail_cat,
                       provider=provider_requested),
                _mk_att(attempt_no=attempt_no, slot_alias=alias,
                        category=fail_cat, correlation_id=correlation_id))
    return fn


_TARGETS = {"a": ["p1/x"], "b": ["p1/y"], "c": ["p2/z"],
            "oracle-judge-local": ["local/m"]}


def test_provider_diverse_retry():
    seen = []
    jp, slot, attempts = _oa._resilient_judge(
        "a", "p", 10, judge_fn=_diverse_stub(seen),
        panel_aliases=["a", "b", "c"], targets=_TARGETS,
        correlation_id="corr-r")
    check("diverse retry: a then c (not b, same provider)",
          seen == ["a", "c"], repr(seen))
    check("diverse retry: served_by c", slot["served_by"] == "c")
    check("diverse retry: all attempts kept", len(attempts) == 2)
    check("diverse retry: corr id propagated",
          all(a.correlation_id == "corr-r" for a in attempts),
          repr([a.correlation_id for a in attempts]))


def test_nonprovider_failure_retries_same_alias():
    seen = []

    def fn(alias, prompt, t, attempt_no=1, provider_requested=None,
           correlation_id=None):
        seen.append(alias)
        if attempt_no == 1:
            return (_mk_jp(alias, valid=False,
                           category=engine.FAILURE_PARSE,
                           provider=provider_requested),
                    _mk_att(attempt_no=attempt_no, slot_alias=alias,
                            category=engine.FAILURE_PARSE,
                            correlation_id=correlation_id))
        return (_mk_jp(alias, posterior=0.6, provider=provider_requested),
                _mk_att(attempt_no=attempt_no, slot_alias=alias,
                        category=engine.FAILURE_OK,
                        correlation_id=correlation_id))

    jp, slot, attempts = _oa._resilient_judge(
        "a", "p", 10, judge_fn=fn, panel_aliases=["a", "b", "c"],
        targets=_TARGETS)
    check("parse failure: same-alias retry", seen == ["a", "a"], repr(seen))
    check("parse failure: attempts preserved", len(attempts) == 2)


def test_local_fallback_fills_slot():
    seen = []
    jp, slot, attempts = _oa._resilient_judge(
        "a", "p", 10,
        judge_fn=_diverse_stub(seen, ok_on=("oracle-judge-local",)),
        panel_aliases=["a", "b", "c"], targets=_TARGETS)
    check("fallback: local attempted", "oracle-judge-local" in seen,
          repr(seen))
    check("fallback: served_by local",
          slot["served_by"] == "oracle-judge-local")
    check("fallback: evidence preserved", len(attempts) == 3,
          repr(len(attempts)))


def test_legacy_judge_fn_still_works():
    """Old-style judge_fn(model, prompt, timeout_s) -> jp keeps working."""
    def fn(model, prompt, t):
        return _mk_jp(model, posterior=0.62, provider="p9")
    jp, slot, attempts = _oa._resilient_judge("a", "p", 10, judge_fn=fn,
                                              panel_aliases=["a"],
                                              targets=_TARGETS)
    check("legacy fn: posterior", abs(jp.posterior - 0.62) < 1e-9)
    check("legacy fn: attempt synthesized", len(attempts) == 1)


# ------------------------------------------------------- failure topology

def test_topology_provider_outage():
    slots = [_slot(False, engine.FAILURE_HTTP_5XX, "p1"),
             _slot(False, engine.FAILURE_TIMEOUT, "p1")]
    r = engine.classify_failures(slots)
    check("topology: provider_outage",
          r["topology"] == engine.TOPO_PROVIDER_OUTAGE, repr(r))


def test_topology_shared_infra():
    slots = [_slot(False, engine.FAILURE_HTTP_5XX, "p1"),
             _slot(False, engine.FAILURE_HTTP_5XX, "p2")]
    r = engine.classify_failures(slots)
    check("topology: shared_infra",
          r["topology"] == engine.TOPO_SHARED_INFRA, repr(r))


def test_topology_genuine_refusal():
    slots = [_slot(False, engine.FAILURE_REFUSAL, "p1", refused=True),
             _slot(False, engine.FAILURE_REFUSAL, "p2", refused=True)]
    r = engine.classify_failures(slots)
    check("topology: genuine_refusal",
          r["topology"] == engine.TOPO_GENUINE_REFUSAL, repr(r))


def test_topology_parse_cascade():
    slots = [_slot(False, engine.FAILURE_PARSE, "p1"),
             _slot(False, engine.FAILURE_SCHEMA, "p2")]
    r = engine.classify_failures(slots)
    check("topology: parse_cascade",
          r["topology"] == engine.TOPO_PARSE_CASCADE, repr(r))


def test_topology_all_ok():
    slots = [_slot(True, engine.FAILURE_OK, "p1")]
    r = engine.classify_failures(slots)
    check("topology: all_ok", r["topology"] == engine.TOPO_ALL_OK, repr(r))


def test_topology_mixed():
    slots = [_slot(False, engine.FAILURE_REFUSAL, "p1", refused=True),
             _slot(False, engine.FAILURE_SCHEMA, "p2")]
    r = engine.classify_failures(slots)
    check("topology: mixed_independent",
          r["topology"] == engine.TOPO_MIXED, repr(r))


def test_topology_no_data():
    r = engine.classify_failures([])
    check("topology: no data", r["topology"] == engine.TOPO_NO_DATA,
          repr(r))


# ------------------------------------------------------- aggregation

def test_same_provider_collapses():
    js = [_mk_jp("a", 0.9, provider="p1"),
          _mk_jp("b", 0.9, provider="p1"),
          _mk_jp("c", 0.9, provider="p1")]
    p3, meta3 = engine.pooled_posterior(0.5, js)
    p1, meta1 = engine.pooled_posterior(0.5, [_mk_jp("a", 0.9,
                                                    provider="p1")])
    check("collapse: 3 same-provider == 1 judge",
          abs(p3 - p1) < 1e-9, "%r vs %r" % (p3, p1))
    check("collapse: one unit of weight across the provider",
          abs(sum(c["weight"] for c in meta3) - 1.0) < 1e-9,
          repr([c["weight"] for c in meta3]))
    check("collapse: contrib records shares",
          all(abs(c["provider_share"] - 1.0 / 3) < 1e-9 for c in meta3))


def test_disagreement_provider_features():
    js = [_mk_jp("a", 0.9, provider="p1"),
          _mk_jp("b", 0.1, provider="p1"),
          _mk_jp("c", 0.9, provider="p2")]
    d = engine.disagreement_features(js)
    check("disagreement: n_providers", d["n_providers"] == 2)
    check("disagreement: concentration == 1 - 2/3",
          abs(d["provider_concentration"] - 1.0 / 3) < 1e-9,
          repr(d["provider_concentration"]))
    diverse = engine.disagreement_features(
        [_mk_jp("a", 0.9, provider="p1"),
         _mk_jp("b", 0.1, provider="p2"),
         _mk_jp("c", 0.9, provider="p3")])
    check("disagreement: concentration penalizes confidence",
          d["confidence"] < diverse["confidence"],
          "%r vs %r" % (d["confidence"], diverse["confidence"]))


# ------------------------------------------------------- calibration/gate

def _fresh_work():
    d = tempfile.mkdtemp(prefix="oracle-rel-")
    cal.CAL_DIR = d
    cal.HISTORY_PATH = os.path.join(d, "accepted_history.jsonl")
    cal.DATASHEET_PATH = os.path.join(d, "judge_datasheets.json")
    cal.CAL_STATE_PATH = os.path.join(d, "calibration_state.json")
    return d


def _seed_history(n, k, source="bench"):
    for i in range(n):
        engine.record_accepted_outcome("q-%d" % i, i < k, source=source)


def test_gate_empty_history_withholds():
    d = _fresh_work()
    try:
        decision, reason = engine.abstention_gate(0.99, 0.99)
        check("gate: empty history withholds despite 0.99/0.99",
              decision == "escalate", repr((decision, reason)))
        check("gate: reason cites n=0", "n=0" in reason
              or "0 labeled" in reason, repr(reason))
        check("gate: no history file created",
              not os.path.exists(cal.HISTORY_PATH))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_gate_38_of_40_emits():
    d = _fresh_work()
    try:
        _seed_history(40, 38)
        decision, reason = engine.abstention_gate(0.9, 0.8)
        op = engine.gate_operating_point()
        check("gate: 38/40 emits", decision == "emit", repr((decision, reason)))
        check("gate: history_n 40, quarantined 0",
              op["history_n"] == 40 and op["quarantined_rows"] == 0,
              repr(op))
        check("gate: served_planned true", op["served_planned"] is True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_gate_19_of_20_withholds():
    d = _fresh_work()
    try:
        _seed_history(20, 19)
        decision, reason = engine.abstention_gate(0.9, 0.8)
        op = engine.gate_operating_point()
        check("gate: 19/20 withholds (finite-sample honesty)",
              decision == "escalate", repr((decision, reason)))
        check("gate: served_planned false", op["served_planned"] is False)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_provenance_quarantine():
    d = _fresh_work()
    try:
        _seed_history(40, 38, source="bench")
        with open(cal.HISTORY_PATH, "a") as f:  # legacy: no label_source
            for i in range(100):
                f.write(json.dumps({"question_id": "legacy-%d" % i,
                                    "correct": True}) + "\n")
        decision, reason = engine.abstention_gate(0.9, 0.8)
        op = engine.gate_operating_point()
        check("quarantine: legacy rows do not inflate history_n",
              op["history_n"] == 40, repr(op))
        check("quarantine: counted", op["quarantined_rows"] == 100,
              repr(op))
        check("quarantine: gate still emits on genuine alone",
              decision == "emit", repr((decision, reason)))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_shrinkage():
    check("shrinkage: 0/0 -> 0.5", engine.shrunk_accuracy(0, 0) == 0.5)
    check("shrinkage: 8/10 -> 10/14",
          abs(engine.shrunk_accuracy(8, 10) - 10.0 / 14) < 1e-9,
          repr(engine.shrunk_accuracy(8, 10)))


def test_no_synthetic_labels():
    d = _fresh_work()
    try:
        _seed_history(3, 2)
        before = open(cal.HISTORY_PATH).read()
        engine.abstention_gate(0.9, 0.8)
        engine.gate_operating_point()
        after = open(cal.HISTORY_PATH).read()
        check("no synthetic labels: history untouched", before == after)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_record_requires_source():
    d = _fresh_work()
    try:
        try:
            engine.record_accepted_outcome("q-x", True)
            check("source required: raises", False)
        except ValueError:
            check("source required: raises", True)
        engine.record_accepted_outcome("q-x", True, source="bench")
        row = json.loads(open(cal.HISTORY_PATH).readline())
        check("source required: written",
              row.get("label_source") == "bench", repr(row))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_operating_point():
    d = _fresh_work()
    try:
        _seed_history(40, 38, source="bench")
        op = engine.gate_operating_point()
        check("operating_point: safety target exposed",
              op["safety_target"] == 0.80, repr(op))
        check("operating_point: counts",
              op["history_n"] == 40 and op["history_k"] == 38, repr(op))
        check("operating_point: shrunk == 40/44",
              abs(op["shrunk_accuracy"] - 40.0 / 44) < 1e-9,
              repr(op["shrunk_accuracy"]))
        check("operating_point: honest bounds",
              op["cp_lo"] < 0.95 <= op["cp_hi"], repr(op))
        check("operating_point: prior reported",
              op["prior_pseudo_n"] == 4.0 and op["prior_mean"] == 0.5,
              repr(op))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_build_verdict_rich():
    d = _fresh_work()
    try:
        framed = {"binary_question": "q?", "resolution_criteria": "c",
                  "base_rate_prior": 0.5, "question_id": "qq",
                  "status": "framed"}
        js = [_mk_jp("a", 0.8, provider="p1"),
              _mk_jp("b", 0.7, provider="p2")]
        for j in js:
            j.attempts = [_mk_att(slot_alias=j.judge_id,
                                 category=engine.FAILURE_OK).to_dict()]
        v = engine.build_verdict(framed, js)
        check("verdict: operating_point", "operating_point" in v)
        check("verdict: failure_topology",
              v["failure_topology"]["topology"] == engine.TOPO_ALL_OK,
              repr(v["failure_topology"]))
        check("verdict: provider_diversity",
              v["provider_diversity"]["n_providers"] == 2,
              repr(v["provider_diversity"]))
        check("verdict: judge_slots with attempts",
              all("attempts" in s for s in v["judge_slots"]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    fns = sorted([v for k, v in list(globals().items())
                  if k.startswith("test_") and callable(v)],
                 key=lambda f: f.__name__)
    for fn in fns:
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("FAIL %s raised %r" % (fn.__name__, e))
            FAILURES.append(fn.__name__)
    print("---")
    if FAILURES:
        print("%d FAILURES: %s"
              % (len(FAILURES), ", ".join(sorted(set(FAILURES)))))
        return 1
    print("all regression tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
