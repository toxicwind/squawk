#!/usr/bin/env python3
"""oracle-ask: the ask path. One command consults the Oracle.

Usage:
  oracle-ask "Will X happen by <date>?" [--json] [--models a,b,c] [--timeout s]
            [--evidence evidence.json] [--canaries] [--no-debate]

Pipeline: frame (fail-closed) -> resilient judge panel in parallel (herd
router) -> pooled posterior (engine owns the number: calibration +
aggregation + gate, exactly once) -> escalation ladder -> verdict JSON on
stdout + verdicts.jsonl.

ROUTER SEPARATION (standing doctrine): this file names only judge ROLE
ALIASES (oracle-judge-a/b/c, oracle-judge-local). Concrete model selection
lives in the herd router config (config/herd.yaml, "Oracle judge panel")
and is owned there exclusively. --models accepts aliases only; concrete
model IDs are rejected. To retarget the panel, edit herd.yaml and restart
herd -- never this file. The provider map below reads ROUTING TOPOLOGY
(which upstream peer an alias forwards to) for failure attribution only;
it never selects, ranks, or prefers models.

Judge models: free-beats-local (SPEC §8.3). The panel shape (3 free-tier
aliases + local fallback) is the proven default from the 2026-09-20 herd
census (see docs/oracle-core.md for the rationale).
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BIN)

import framing  # noqa: E402  (after sys.path.insert for sibling-dir import)
import calibration as cal  # noqa: E402  (after sys.path.insert for sibling-dir import)
import engine  # noqa: E402  (after sys.path.insert for sibling-dir import)
import evidence as evmod  # noqa: E402  (after sys.path.insert for sibling-dir import)
import escalation  # noqa: E402  (after sys.path.insert for sibling-dir import)

HERD_URL = os.environ.get("HERD_URL", "http://127.0.0.1:25100")
WORK = os.environ.get("ORACLE_WORK", "/home/toxic/estate/ranch/squawk/oracle/work")

# Judge panel: ROUTER ROLE ALIASES. Concrete targets are owned by
# config/herd.yaml ("Oracle judge panel"); this list is routing surface
# only, never model-family selection.
DEFAULT_JUDGES = [
    "oracle-judge-a",
    "oracle-judge-b",
    "oracle-judge-c",
]
FALLBACK_JUDGE = "oracle-judge-local"  # local last resort, router-owned

JUDGE_PROMPT = """You are judge {idx} (anonymous) on the OpenFang Oracle panel.
Question: {question}
Resolution criteria: {criteria}
Base-rate prior: {prior:.2f} (start here; move only on evidence).

First argue BOTH sides to yourself in one line each, then judge.
OVERCONFIDENCE ADVISORY: judges are systematically overconfident. Report a
posterior above 0.90 or below 0.10 only if you would stake your own money on it.

Reply with JSON ONLY, no other text:
{{"posterior": <0..1, probability the answer is YES>,
  "verbal_confidence": "<low|medium|high>",
  "claims": [{{"text": "<one atomic factual claim>",
               "stance": "<supports_yes|supports_no|neutral>",
               "llr": <signed strength in nats, |llr|<=2.0>,
               "cluster_id": "<shared id when the same underlying fact>",
               "rationale": "<one line>", "urls": [],
               "credibility": "<low|medium|high>"}}],
  "reasoning_summary": "<2-3 sentences>"}}"""


def _env_models():
    raw = os.environ.get("ORACLE_JUDGES", ",".join(DEFAULT_JUDGES))
    return [m.strip() for m in raw.split(",") if m.strip()]


def _alias_allowlist():
    extra = [m.strip() for m in os.environ.get("ORACLE_JUDGES", "").split(",")
             if m.strip()]
    return set(DEFAULT_JUDGES + [FALLBACK_JUDGE] + extra)


def _check_alias_models(models):
    """Fail closed: only router aliases may serve as judges. Concrete
    model IDs (with /, :, or known family names) are never accepted --
    model selection lives in herd.yaml, not here."""
    bad = [m for m in models if m not in _alias_allowlist()]
    if bad:
        raise SystemExit(
            "refusing non-alias judge model(s): %s. Model selection lives "
            "in the herd router config (config/herd.yaml); add panel "
            "aliases via ORACLE_JUDGES." % ", ".join(bad))


# ---------------------------------------------------------------------------
# routing topology (failure attribution only — never model selection)
# ---------------------------------------------------------------------------

HERD_YAML = os.environ.get("HERD_YAML",
                           "/home/toxic/estate/config/herd.yaml")
_provider_targets_cache = None


def alias_router_targets():
    """{alias: [target, standby, ...]} from herd.yaml cmd lines.

    Regex scan only (no yaml dependency). Reads ROUTING TOPOLOGY — which
    upstream peer an alias forwards to — for failure attribution. Missing
    or unparseable config -> {} and providers are honestly 'unknown'.
    """
    global _provider_targets_cache
    if _provider_targets_cache is not None:
        return _provider_targets_cache
    out = {}
    try:
        with open(HERD_YAML) as f:
            text = f.read()
    except Exception:
        _provider_targets_cache = out
        return out
    alias = None
    for line in text.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_.\-/]+):\s*$", line)
        if m:
            alias = m.group(1)
            continue
        if alias and line.startswith("    cmd:"):
            targets = re.findall(r"--(?:target|standby)\s+(\S+)", line)
            if targets:
                out[alias] = targets
            alias = None  # only the cmd line carries the route
    _provider_targets_cache = out
    return out


def provider_of_alias(alias, targets=None):
    """Infrastructure provider (upstream peer) for an alias, e.g.
    'openrouter-free'. First path segment of the primary target."""
    tgts = (targets if targets is not None
            else alias_router_targets()).get(alias) or []
    return tgts[0].split("/")[0] if tgts else "unknown"


def family_of_model(model_id):
    """Model org/family from a served model id, e.g. 'nex-agi'."""
    return (model_id or "").split("/")[0] or "unknown"


# ---------------------------------------------------------------------------
# herd transport: structured results, evidence preserved
# ---------------------------------------------------------------------------

def herd_chat(model, prompt, timeout_s=90, max_tokens=1500):
    """POST /v1/chat/completions. Returns a structured dict — never raises.

    On success: ok, text, latency_s, usage, http_status, model_served
    (the resolved model id from the response body), provider_served,
    refusal (upstream refusal field), server header.
    On failure: ok=False, error, error_kind (http|timeout|connection|
    unknown), http_status (when the upstream answered), error_body
    (bounded upstream body excerpt — the evidence old code dropped).
    """
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        HERD_URL + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            status = r.status
            server = r.headers.get("Server")
            data = json.load(r)
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        return {"ok": True, "text": msg.get("content"),
                "latency_s": time.time() - t0,
                "usage": data.get("usage") or {},
                "http_status": status,
                "model_served": data.get("model"),
                "provider_served": data.get("provider"),
                "refusal": msg.get("refusal"),
                "server": server,
                "error": None, "error_kind": None, "error_body": None}
    except urllib.error.HTTPError as e:
        try:
            ebody = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            ebody = ""
        return {"ok": False,
                "error": "HTTPError %s: %s" % (e.code, e.reason),
                "error_kind": "http", "http_status": e.code,
                "error_body": ebody, "latency_s": time.time() - t0,
                "usage": {}, "text": None,
                "model_served": None, "provider_served": None,
                "refusal": None, "server": None}
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e) or e)
        kind = ("timeout" if "timed out" in reason.lower()
                or isinstance(getattr(e, "reason", None), TimeoutError)
                else "connection")
        return {"ok": False, "error": "URLError: %s" % reason,
                "error_kind": kind, "http_status": None,
                "error_body": None, "latency_s": time.time() - t0,
                "usage": {}, "text": None,
                "model_served": None, "provider_served": None,
                "refusal": None, "server": None}
    except (TimeoutError, socket.timeout) as e:
        return {"ok": False, "error": "timeout: %s" % e,
                "error_kind": "timeout", "http_status": None,
                "error_body": None, "latency_s": time.time() - t0,
                "usage": {}, "text": None,
                "model_served": None, "provider_served": None,
                "refusal": None, "server": None}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                "error_kind": "unknown", "http_status": None,
                "error_body": None, "latency_s": time.time() - t0,
                "usage": {}, "text": None,
                "model_served": None, "provider_served": None,
                "refusal": None, "server": None}


def _error_category(res):
    """Transport result -> failure taxonomy category."""
    kind = res.get("error_kind")
    status = res.get("http_status")
    if kind == "timeout" or status == 408:
        return engine.FAILURE_TIMEOUT
    if kind == "connection":
        return engine.FAILURE_CONN
    if status == 429:
        return engine.FAILURE_HTTP_429
    if status == 402:
        return engine.FAILURE_HTTP_402
    if isinstance(status, int) and status >= 500:
        return engine.FAILURE_HTTP_5XX
    if isinstance(status, int) and status >= 400:
        return engine.FAILURE_HTTP_4XX
    if kind == "http":
        return engine.FAILURE_HTTP_5XX  # answered but status unreadable
    return engine.FAILURE_UNKNOWN


REFUSAL_PATTERNS = (
    "i can't", "i cannot", "i'm unable", "i am unable",
    "unable to comply", "unable to answer", "against my",
    "refuse to", "decline to", "not able to",
)


def _looks_like_refusal(text):
    t = (text or "").lower()
    return any(p in t for p in REFUSAL_PATTERNS)


def extract_json(text):
    """Robust JSON extraction: first balanced {...} block."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    instr = esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
        else:
            if ch == '"':
                instr = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
    return None


def judge_once(model, prompt, timeout_s, attempt_no=1, provider_requested=None,
               correlation_id=None):
    """One judge call -> (JudgePosterior, JudgeAttempt).

    Genuine refusals (HTTP 200 + upstream refusal signal or refusal text)
    are marked refused and contribute nothing (never fabricated).
    Transport errors, timeouts, and parse/schema failures are marked
    valid=False with a failure_category — evidence about the pipeline,
    never mislabeled as a judge's refusal.
    """
    res = herd_chat(model, prompt, timeout_s)
    err = res.get("error")
    if res.get("error_body"):
        # the upstream body's bounded excerpt is first-class evidence
        # (provider error shapes, quota states) — never dropped.
        err = ((err + " | upstream body: " + res["error_body"]) if err
               else res["error_body"])
    att = engine.JudgeAttempt(
        attempt_no=attempt_no, slot_alias=model,
        provider_requested=provider_requested,
        latency_s=res.get("latency_s", 0),
        http_status=res.get("http_status"),
        correlation_id=correlation_id,
        error_excerpt=err,
        response_excerpt=res.get("text"))
    jp = engine.JudgePosterior(judge_id=model, posterior=0.5, refused=False,
                               valid=False,
                               failure_category=engine.FAILURE_UNKNOWN,
                               provider=provider_requested)
    jp.raw_response = (res.get("text") or "")[:2000]
    jp.latency_s = res.get("latency_s", 0)
    jp.error = res.get("error")
    jp.usage = res.get("usage") or {}
    if not res["ok"]:
        cat = _error_category(res)
        att.failure_category = cat
        jp.failure_category = cat
        return jp, att
    att.model_served = res.get("model_served")
    att.provider_served = res.get("provider_served")
    jp.model_family = family_of_model(res.get("model_served"))
    text = res.get("text") or ""
    if res.get("refusal") is not None or _looks_like_refusal(text):
        att.failure_category = engine.FAILURE_REFUSAL
        jp.failure_category = engine.FAILURE_REFUSAL
        jp.refused = True
        return jp, att
    data = extract_json(text)
    if not isinstance(data, dict):
        att.failure_category = engine.FAILURE_PARSE
        jp.failure_category = engine.FAILURE_PARSE
        return jp, att
    if "posterior" not in data:
        att.failure_category = engine.FAILURE_SCHEMA
        jp.failure_category = engine.FAILURE_SCHEMA
        return jp, att
    try:
        p = float(data.get("posterior"))
    except (TypeError, ValueError):
        att.failure_category = engine.FAILURE_SCHEMA
        jp.failure_category = engine.FAILURE_SCHEMA
        return jp, att
    if math.isnan(p) or math.isinf(p):
        att.failure_category = engine.FAILURE_SCHEMA
        jp.failure_category = engine.FAILURE_SCHEMA
        return jp, att
    claims = []
    for c in data.get("claims") or []:
        if isinstance(c, dict) and c.get("text"):
            claims.append(c)
    jp.valid = True
    jp.refused = False
    jp.posterior = min(0.999, max(0.001, p))
    jp.verbal_conf = data.get("verbal_confidence")
    jp.claims = claims
    att.failure_category = engine.FAILURE_OK
    jp.failure_category = engine.FAILURE_OK
    return jp, att


def _resilient_judge(model, prompt, timeout_s, judge_fn=None,
                     panel_aliases=None, targets=None, correlation_id=None):
    """One panel slot with provider-diverse fail-fast redundancy.

    Attempt 1: the slot alias. Attempt 2: on a provider-class failure
    (timeout / 5xx / 429 / 402 / connection — the PROVIDER is implicated,
    not the alias), the first panel alias served by a DIFFERENT provider
    (FrugalGPT cascade logic: never re-roll a dead provider); otherwise a
    bounded same-alias retry at half timeout. Attempt 3: the local-fallback
    alias (separate infrastructure) fills the slot.

    Returns (JudgePosterior, slot_info, [JudgeAttempt]). ALL attempts are
    preserved — the verdict ledger keeps the evidence, not just the
    outcome. A failed slot never silently shrinks the panel: slot_info
    records who actually served it, and the failure topology classifier
    (engine.classify_failures) attributes correlated failures to the
    provider instead of counting them as independent judge failures.
    """
    judge_fn = judge_fn or judge_once
    targets = targets if targets is not None else alias_router_targets()
    panel = panel_aliases or _env_models()
    prov = provider_of_alias(model, targets)
    attempts = []

    def _call(alias, t, no):
        preq = provider_of_alias(alias, targets)
        try:
            out = judge_fn(alias, prompt, t, attempt_no=no,
                           provider_requested=preq,
                           correlation_id=correlation_id)
        except TypeError:
            # legacy judge_fn(model, prompt, timeout_s) -> JudgePosterior
            out = judge_fn(alias, prompt, t)
        if isinstance(out, tuple):
            jp, att = out
        else:
            legacy = out
            refused = bool(getattr(legacy, "refused", False))
            valid = bool(getattr(legacy, "valid", not refused))
            jp = engine.JudgePosterior(
                judge_id=getattr(legacy, "judge_id", alias),
                posterior=getattr(legacy, "posterior", 0.5),
                refused=refused, valid=valid, provider=preq,
                failure_category=(engine.FAILURE_REFUSAL if refused
                                  else engine.FAILURE_OK if valid
                                  else engine.FAILURE_UNKNOWN))
            att = engine.JudgeAttempt(
                attempt_no=no, slot_alias=alias,
                provider_requested=preq, correlation_id=correlation_id,
                failure_category=jp.failure_category,
                latency_s=getattr(legacy, "latency_s", 0),
                error_excerpt=getattr(legacy, "error", None),
                response_excerpt=getattr(legacy, "raw_response", None))
        attempts.append(att)
        if not getattr(jp, "provider", None):
            jp.provider = att.provider_requested
        return jp

    jp = _call(model, timeout_s, 1)
    served_by = model
    if not jp.live:
        if getattr(jp, "failure_category", engine.FAILURE_UNKNOWN) \
                in engine.PROVIDER_CLASS_FAILURES:
            alt = next((a for a in panel
                        if a != model and a != FALLBACK_JUDGE
                        and provider_of_alias(a, targets) not in (prov, "unknown")),
                       None)
            if alt is not None:
                jp = _call(alt, min(timeout_s, 45.0) / 2.0, 2)
                if jp.live:
                    served_by = alt
            else:
                jp = _call(model, min(timeout_s, 45.0) / 2.0, 2)
        else:
            jp = _call(model, min(timeout_s, 45.0) / 2.0, 2)
    if not jp.live and model != FALLBACK_JUDGE:
        fb = _call(FALLBACK_JUDGE, 60.0, len(attempts) + 1)
        if fb.live:
            jp = fb
            served_by = FALLBACK_JUDGE
        else:
            jp = fb
    if served_by == FALLBACK_JUDGE:
        jp.judge_id = FALLBACK_JUDGE
    slot = {"slot": model, "served_by": served_by,
            "refused": jp.refused, "valid": jp.valid,
            "failure_category": jp.failure_category,
            "provider_requested": prov,
            "provider_serving": jp.provider,
            "attempts": len(attempts)}
    return jp, slot, attempts


def load_datasheets():
    if os.path.exists(cal.DATASHEET_PATH):
        try:
            with open(cal.DATASHEET_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def run_ask(question, models=None, timeout_s=90, evidence_items=None,
            allow_debate=True, budget_s=240):
    """Full ask pipeline. Returns the verdict dict.

    Calibration ownership: engine.build_verdict is the SOLE applier of
    calibration. This function never touches judge posteriors between
    receipt and the engine (double application was removed 2026-09-20).

    Every judge attempt is persisted in verdict["judge_attempts"] with its
    structured record (error, failure category, HTTP status, requested /
    served provider and model, latency, bounded excerpts, correlation id).
    """
    t0 = time.time()
    t_f0 = time.time()
    framed = framing.frame_question(question)
    t_frame = time.time() - t_f0
    if framed.get("status") == "refused":
        return engine.build_verdict(framed, [])
    models = models or _env_models()
    _check_alias_models(models)
    datasheets = load_datasheets()
    targets = alias_router_targets()
    correlation_id = uuid.uuid4().hex[:16]

    # evidence partitions (asymmetry) — empty for pure-judgment asks
    partition = None
    if evidence_items:
        partition = evmod.partition_evidence(evidence_items, len(models))

    def prompt_for(i):
        base = JUDGE_PROMPT.format(
            idx=i + 1, question=framed["binary_question"],
            criteria=framed["resolution_criteria"],
            prior=framed["base_rate_prior"])
        if partition:
            base += ("\n\nEVIDENCE VIEW:\n" +
                     evmod.summarize_evidence_for_judge(partition, i))
        return base

    calls = 0
    judges = []
    latencies = {}
    slots = []
    usages = []
    judge_attempts = {}
    t_j0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=len(models)) as ex:
        futs = {ex.submit(_resilient_judge, m, prompt_for(i), timeout_s,
                          None, models, targets, correlation_id): (m, i)
                for i, m in enumerate(models)}
        deadline = t0 + budget_s
        for fut in cf.as_completed(futs):  # no outer timeout: its TimeoutError
            # escaped uncaught with pending futures. Every slot is
            # time-bounded by construction and each fut.result() below
            # is deadline-bounded, so this loop always terminates.
            m, i = futs[fut]
            try:
                jp, slot, attempts = fut.result(
                    timeout=max(1, deadline - time.time()))
            except Exception as e:
                jp = engine.JudgePosterior(judge_id=m, posterior=0.5,
                                           refused=False, valid=False,
                                           failure_category=
                                           engine.FAILURE_EXECUTOR)
                jp.error = "executor: %s" % e
                slot = {"slot": m, "served_by": m, "refused": False,
                        "valid": False,
                        "failure_category": engine.FAILURE_EXECUTOR,
                        "provider_requested": provider_of_alias(m, targets),
                        "provider_serving": None, "attempts": 0}
                attempts = []
            calls += len(attempts)  # actual requests, incl. retries/fallbacks
            ds = datasheets.get(jp.judge_id, datasheets.get(m, {}))
            jp.reliability = float(ds.get("reliability", 1.0))
            jp.cal_weight = 1.0
            jp.attempts = [a.to_dict() for a in attempts]
            judges.append(jp)
            slots.append(slot)
            latencies[m] = getattr(jp, "latency_s", 0)
            usages.append(getattr(jp, "usage", None) or {})
            judge_attempts[m] = jp.attempts
    t_judge = time.time() - t_j0
    judges.sort(key=lambda j: models.index(j.judge_id)
                if j.judge_id in models else 99)

    # NOTE: no calibration here. engine.build_verdict applies the
    # calibration loop exactly once, deterministically, then aggregates.
    t_e0 = time.time()
    verdict = engine.build_verdict(framed, judges)
    t_engine = time.time() - t_e0
    verdict["timing"] = {"frame_s": round(t_frame, 3),
                         "judge_s": round(t_judge, 3),
                         "engine_s": round(t_engine, 3)}
    verdict["latency_s"] = time.time() - t0
    verdict["judge_latencies"] = latencies
    verdict["judge_slots"] = slots
    verdict["judge_attempts"] = judge_attempts
    verdict["correlation_id"] = correlation_id
    verdict["models"] = models

    # escalation ladder: route on the ABSTENTION decision (the emission gate),
    # not the full RefusalGate ledger (which stays strict/honest by design:
    # NOT_CHECKED never passes silently, but it routes via limitations).
    gate_ok = (verdict["status"] == "verdict")
    live_posts = [j.posterior for j in judges if engine.is_live(j)]
    tier, tier_reason = escalation.route(
        live_posts, verdict["structural_confidence"]["confidence"], gate_ok)
    verdict["tier"] = tier
    verdict["tier_reason"] = tier_reason
    if tier == "DEBATE" and allow_debate:
        ev_text = "\n".join(
            "- " + (c.get("text", "") or "") for j in judges for c in j.claims[:4])

        debate_usages = []

        def _debate_chat(model, prompt, t):
            res = herd_chat(model, prompt, t, max_tokens=400)
            debate_usages.append(res.get("usage") or {})
            return {"content": res.get("text") or ""}

        budget_left = max(10.0, budget_s - (time.time() - t0))
        t_d0 = time.time()
        debate = escalation.debate_tier(
            framed["binary_question"], framed["resolution_criteria"], ev_text,
            judges=models,  # router aliases; distinct per advocate
            chat_fn=_debate_chat,
            k=escalation.DEBATE_K, max_rounds=escalation.DEBATE_MAX_ROUNDS,
            eps=escalation.DEBATE_EPS,
            per_advocate_timeout_s=min(90.0, budget_left / 2.0))
        calls += debate.get("requests",
                        debate["rounds"] * len(debate["advocate_finals"]))
        # Engine re-owns the debate output: advocate finals become
        # half-weight judges (they share one converged trajectory, so
        # k advocates/side ~= 1 independent judge/side of evidence).
        # Gates, confidence, contributions, and the verdict hash are all
        # recomputed on the final number -- the vote verdict is kept only
        # for provenance. Nothing is overwritten in place.
        adv_judges = [
            engine.JudgePosterior(judge_id=a["model"],
                                  posterior=a["posterior"], cal_weight=0.5)
            for a in debate["advocate_finals"]]
        final = engine.build_verdict(framed, adv_judges)
        final["tier"] = "DEBATE"
        final["tier_reason"] = (
            "structured advocate debate: %d rounds%s"
            % (debate["rounds"],
               ", converged" if debate["converged"] else ", budget-capped"))
        final["debate"] = {
            "rounds": debate["rounds"],
            "converged": debate["converged"],
            "internal_posterior": debate["posterior"],
            "advocate_finals": debate["advocate_finals"],
            "vote_probability": verdict["probability"],
            "vote_status": verdict["status"],
            "vote_tier": verdict["tier"],
        }
        final["vote_verdict"] = verdict  # provenance, not the decision
        final["judge_slots"] = slots
        final["judge_attempts"] = judge_attempts
        final["correlation_id"] = correlation_id
        final["judge_latencies"] = latencies
        final["models"] = models
        final["latency_s"] = time.time() - t0
        final["timing"] = dict(verdict.get("timing") or {},
                               debate_s=round(time.time() - t_d0, 3))
        final["cost_usd"] = round(calls * 0.002, 6)
        final["llm_calls"] = calls
        final["usage_cost_usd"] = round(
            sum(_usage_cost(u) for u in usages + debate_usages), 6)
        engine.record_verdict(final)
        return final
    elif tier == "HUMAN":
        path = escalation.flag_human(framed, tier_reason,
                                     {"verdict": verdict["probability"]})
        verdict["human_flag"] = path
    elif verdict["status"] == "escalate" and tier == "VOTE":
        # gate withheld but no disagreement: escalate path stays, engine honest
        verdict["tier"] = "VOTE"
    verdict["cost_usd"] = round(calls * 0.002, 6)
    verdict["llm_calls"] = calls
    verdict["usage_cost_usd"] = round(sum(_usage_cost(u) for u in usages), 6)
    engine.record_verdict(verdict)
    return verdict


def _usage_cost(u):
    """Measured upstream cost of one herd call from its usage block.
    Free-tier judges report cost 0; missing usage -> 0.0 (honest, not
    imputed). Kept separate from cost_usd, which is the code's flat
    per-request accounting estimate."""
    if not isinstance(u, dict):
        return 0.0
    c = u.get("cost")
    try:
        return float(c) if c else 0.0
    except (TypeError, ValueError):
        return 0.0


def run_canaries(models=None, timeout_s=90):
    """Ask every seeded canary; returns per-judge gaming report."""
    import glob
    reports = []
    for path in sorted(glob.glob(os.path.join(BIN, "..", "bench",
                                              "canary_*.json"))):
        with open(path) as f:
            spec = json.load(f)
        v = run_ask(spec["question"], models=models, timeout_s=timeout_s,
                    allow_debate=False)
        reports.append({"canary": os.path.basename(path),
                        "answer": spec["answer"],
                        "verdict_p": v.get("probability"),
                        "correct": ((v.get("probability", 0.5) >= 0.5)
                                    == bool(spec["answer"]))
                        if v.get("status") == "verdict" else None,
                        "status": v.get("status")})
    return reports


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ask the OpenFang Oracle.")
    ap.add_argument("question", nargs="?", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--models", default=",".join(_env_models()),
                    help="comma-separated herd judge aliases "
                         "(router role aliases only; concrete model IDs "
                         "are refused)")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--budget", type=float, default=240)
    ap.add_argument("--evidence", default=None, help="JSON file of evidence items")
    ap.add_argument("--canaries", action="store_true")
    ap.add_argument("--no-debate", action="store_true")
    args = ap.parse_args(argv)

    if args.canaries:
        rep = run_canaries(models=args.models.split(","), timeout_s=args.timeout)
        print(json.dumps(rep, indent=2))
        return 0
    if not args.question:
        ap.error("a question is required (or --canaries)")
    items = None
    if args.evidence:
        with open(args.evidence) as f:
            items = json.load(f)
    verdict = run_ask(args.question, models=args.models.split(","),
                      timeout_s=args.timeout, evidence_items=items,
                      allow_debate=not args.no_debate, budget_s=args.budget)
    if args.json or True:
        print(json.dumps(verdict, indent=2, default=str))
    return 0 if verdict.get("status") in ("verdict", "escalate") else 3


if __name__ == "__main__":
    sys.exit(main())
