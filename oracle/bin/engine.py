#!/usr/bin/env python3
"""Deterministic aggregation engine — the Oracle's constitutional core.

CONSTITUTIONAL RULE: the deterministic engine owns every number it emits —
verdicts, probabilities, confidence, payouts. LLM judges are advisors
producing structured, attributable inputs (posteriors, per-claim LLRs).
No LLM output ever bypasses this engine. The engine's acceptance checks
outrank every judge. (Borrow: PROCTOR arXiv:2609.02246; Raven-Agent
arXiv:2607.03015; see docs/BORROWS.md.)

Layer 3 per the research design:
  * pooled posterior via product-of-posteriors (Blackwell bound,
    arXiv:2605.06028): each judge reports a posterior; the engine combines
    in log-odds with calibration weights x datasheet reliability, collapsed
    so one infrastructure provider contributes one unit of weight no matter
    how many aliases route through it (arXiv:2306.05685: repeated calls
    through shared bias structure are not independent evidence).
  * confidence from DISAGREEMENT STRUCTURE (DiscoUQ, arXiv:2603.20975) —
    evidence overlap, stance divergence, confidence spread, provider
    diversity — never raw vote margins.
  * every verdict ships bias-corrected point estimate + CI (judge-reporting
    math), a limitations line (CJE-style NOT_CHECKED), the full structured
    attempt record for every judge call, and the safety-vs-served-traffic
    operating point.
  * abstention gate with finite-sample Clopper-Pearson guarantee
    (arXiv:2608.17994): below-threshold verdicts escalate, never emitted.
    Certified availability is a plannable resource (arXiv:2609.22048):
    with n labeled outcomes the gate certifies exactly what the
    exact-binomial lower bound supports — no binary cold-start wall, no
    unanimity bypass, no synthetic history rows. Prior shrinkage keeps
    small-n estimates honest; only genuinely labeled rows
    (label_source in LABEL_SOURCES) count as evidence.
  * failure topology classification (arXiv:2609.22056): transport failures
    are attributed to providers, not slots — a correlated provider outage
    is never mistaken for independent judge failures, and parser/schema
    failures are never mistaken for genuine model refusals.
  * canary checks: seeded known-answer questions where a perfect-but-wrong
    pattern exposes gaming (feeds stake-and-slash evidence).
"""
import hashlib
import json
import math
import os
import time

import bayes
import calibration as cal

WORK = os.environ.get("ORACLE_WORK", "/home/toxic/estate/projects/range/ranch/oracle/work")
VERDICT_LEDGER = os.path.join(WORK, "verdicts.jsonl")
CANARY_PATH = os.path.join(WORK, "canaries.json")

# Abstention-gate defaults (proven values documented in docs/oracle-core.md).
GATE_ALPHA = 0.05          # FDR target among emitted verdicts
GATE_MIN_ACCURACY = 0.80   # CP lower bound on accepted-set accuracy to emit
AUTO_P = 0.85              # unanimity auto-resolve posterior bar

# Prior shrinkage for the accepted-set accuracy estimate. An explicit
# pseudo-count prior (never synthetic labeled rows): with n=0 labels the
# estimate is exactly the prior mean, and the CP lower bound is 0, so the
# gate withholds — selective output, not a wall with a bypass hatch.
PRIOR_PSEUDO_N = 4.0
PRIOR_MEAN = 0.5

# Label provenance lives in calibration (the history owner): only rows
# with an explicit label_source in cal.LABEL_SOURCES count as evidence.
# Legacy rows without a source are quarantined (counted, never used).
# Nothing in this module ever writes synthetic labels.
LABEL_SOURCES = cal.LABEL_SOURCES

# ---- failure taxonomy (attempt-level; persisted on every judge call) ----
FAILURE_OK = "ok"
FAILURE_REFUSAL = "refusal"            # genuine model refusal (200 + refusal signal)
FAILURE_PARSE = "parse_failure"        # 200 but no JSON object extractable
FAILURE_SCHEMA = "schema_failure"      # JSON parsed but posterior missing/invalid
FAILURE_TIMEOUT = "timeout"
FAILURE_HTTP_5XX = "http_5xx"
FAILURE_HTTP_429 = "http_429"
FAILURE_HTTP_402 = "http_402"
FAILURE_HTTP_4XX = "http_4xx"
FAILURE_CONN = "connection_error"
FAILURE_EXECUTOR = "executor_error"
FAILURE_UNKNOWN = "unknown"

# Failure classes that indict the PROVIDER (shared infrastructure), not the
# alias: the retry cascade must switch providers instead of retrying the
# same alias (FrugalGPT cascade logic, arXiv:2305.05176).
PROVIDER_CLASS_FAILURES = frozenset({
    FAILURE_TIMEOUT, FAILURE_HTTP_5XX, FAILURE_HTTP_429, FAILURE_HTTP_402,
    FAILURE_CONN,
})

# ---- failure topologies (panel-level classification) ----
TOPO_ALL_OK = "all_ok"
TOPO_PROVIDER_OUTAGE = "provider_outage"
TOPO_SHARED_INFRA = "shared_infra"
TOPO_PARSE_CASCADE = "parse_cascade"
TOPO_GENUINE_REFUSAL = "genuine_refusal"
TOPO_MIXED = "mixed_independent"
TOPO_NO_DATA = "unknown_no_attempt_data"


class JudgeAttempt:
    """One structured judge-call attempt. Every field is persisted."""

    __slots__ = ("attempt_no", "slot_alias", "provider_requested",
                 "model_served", "provider_served", "http_status",
                 "failure_category", "latency_s", "error_excerpt",
                 "response_excerpt", "correlation_id")

    def __init__(self, attempt_no, slot_alias, provider_requested=None,
                 model_served=None, provider_served=None, http_status=None,
                 failure_category=FAILURE_UNKNOWN, latency_s=0.0,
                 error_excerpt=None, response_excerpt=None,
                 correlation_id=None):
        self.attempt_no = attempt_no
        self.slot_alias = slot_alias
        self.provider_requested = provider_requested
        self.model_served = model_served
        self.provider_served = provider_served
        self.http_status = http_status
        self.failure_category = failure_category
        self.latency_s = latency_s
        self.error_excerpt = (error_excerpt or "")[:500]
        self.response_excerpt = (response_excerpt or "")[:500]
        self.correlation_id = correlation_id

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


class JudgePosterior:
    def __init__(self, judge_id, posterior, cal_weight=1.0, reliability=1.0,
                 verbal_conf=None, claims=None, refused=False, valid=True,
                 failure_category=FAILURE_OK, provider=None, model_family=None,
                 attempts=()):
        self.judge_id = judge_id
        self.posterior = min(0.999, max(0.001, float(posterior)))
        self.cal_weight = float(cal_weight)
        self.reliability = float(reliability)
        self.verbal_conf = verbal_conf
        self.claims = claims or []   # atomic claims: {cluster_id, stance, ...}
        # refused=True ONLY for genuine model refusals. Transport errors,
        # timeouts, and parse/schema failures set valid=False instead —
        # they are evidence about the pipeline, not a judge's abstention.
        self.refused = refused
        self.valid = valid
        self.failure_category = failure_category
        self.provider = provider            # infra provider (peer), e.g. openrouter-free
        self.model_family = model_family    # model org/family, e.g. nex-agi
        self.attempts = list(attempts or [])  # JudgeAttempt.to_dict() list

    @property
    def weight(self):
        return self.cal_weight * self.reliability

    @property
    def live(self):
        """A live judge contributes a usable posterior. Everything else —
        refusal, transport failure, parse failure — contributes nothing but
        its attempt record."""
        return self.valid and not self.refused


def is_live(j):
    return bool(getattr(j, "live", False))


def _provider_of(j):
    return getattr(j, "provider", None) or "unknown"


def pooled_posterior(prior, judges, provider_collapse=True):
    """Product-of-posteriors in log-odds space (Blackwell bound).

    L = logit(prior) + sum_i w_i * logit(calibrated_posterior_i).
    Judges advise; the engine decides. Only live judges contribute.

    provider_collapse: one infrastructure provider contributes one unit of
    total weight, split among its aliases by their individual weights.
    Three aliases through one keypool are one partially-independent source,
    not three (arXiv:2306.05685: repeated calls through shared bias
    structure do not average out). Each contrib entry records the raw
    weight, the provider share, and the collapsed weight actually applied.
    """
    live = [j for j in judges if is_live(j)]
    if not live:
        return prior, []
    prov_mass = {}
    for j in live:
        prov_mass[_provider_of(j)] = prov_mass.get(_provider_of(j), 0.0) + j.weight
    lo = bayes.logit(prior)
    contrib = []
    for j in live:
        prov = _provider_of(j)
        share = j.weight / prov_mass[prov] if prov_mass[prov] else 0.0
        w = share if provider_collapse else j.weight
        c = w * bayes.logit(j.posterior)
        lo += c
        contrib.append({"judge": j.judge_id, "provider": prov,
                        "model_family": getattr(j, "model_family", None),
                        "weight_raw": j.weight, "provider_share": share,
                        "weight": w, "posterior": j.posterior,
                        "logit_contrib": c})
    post = bayes.inv_logit(lo)
    return min(bayes.PROB_CEIL, max(bayes.PROB_FLOOR, post)), contrib


def disagreement_features(judges):
    """DiscoUQ-lite: confidence from disagreement STRUCTURE, not vote margins.
    Features: evidence overlap (Jaccard of cluster_ids), stance divergence,
    posterior spread, provider diversity. Returns dict with a structural
    confidence in [0,1]."""
    live = [j for j in judges if is_live(j)]
    if len(live) < 2:
        return {"confidence": 0.5, "note": "single judge — no structure",
                "n_judges": len(live), "n_providers": len({ _provider_of(j) for j in live }),
                "providers": sorted({_provider_of(j) for j in live}),
                "provider_concentration": 0.0}
    posts = [j.posterior for j in live]
    mean = sum(posts) / len(posts)
    spread = math.sqrt(sum((p - mean) ** 2 for p in posts) / len(posts))
    # evidence overlap: Jaccard over cluster id sets
    sets = [set(c.get("cluster_id", "") for c in j.claims if c.get("cluster_id"))
            for j in live]
    pairwise = []
    for a in range(len(sets)):
        for b in range(a + 1, len(sets)):
            u = sets[a] | sets[b]
            pairwise.append(len(sets[a] & sets[b]) / len(u) if u else 1.0)
    overlap = sum(pairwise) / len(pairwise) if pairwise else 1.0
    # stance divergence: fraction of judges on the minority side of 0.5
    yes = sum(1 for p in posts if p >= 0.5)
    divergence = min(yes, len(posts) - yes) / len(posts)
    # provider diversity: judges through one provider share failure modes
    # AND bias structure (arXiv:2306.05685 position/verbosity/self-enhancement
    # biases do not average out across calls sharing a provider).
    providers = sorted({_provider_of(j) for j in live})
    n_providers = len(providers)
    concentration = 1.0 - n_providers / len(live)
    # structural confidence: high when judges agree on INDEPENDENT evidence
    # (low overlap + low spread) from DIVERSE providers, low when they herd
    # on the same evidence (high overlap), genuinely diverge
    # (high spread/divergence), or share one provider (high concentration).
    independence = 1.0 - overlap
    agreement = 1.0 - min(1.0, spread * 4.0)
    base = min(1.0, max(0.0,
                        0.5 * agreement + 0.3 * independence
                        + 0.2 * (1.0 - divergence * 2.0)))
    diversity_factor = 0.5 + 0.5 * (n_providers / len(live))
    confidence = base * diversity_factor
    return {"confidence": confidence, "spread": spread,
            "evidence_overlap": overlap, "stance_divergence": divergence,
            "n_judges": len(live), "n_providers": n_providers,
            "providers": providers,
            "provider_concentration": concentration}


def classify_failures(slots):
    """Panel-level failure topology from structured attempt records.

    slots: list of {slot, served_by, attempts: [attempt dicts],
                   refused, valid, failure_category}. Never mistakes a
    correlated provider outage for independent judge failures
    (arXiv:2609.22056: failures cluster in structurally predictable
    subpopulations — attribute them to the structure).
    """
    if not slots:
        return {"topology": TOPO_NO_DATA, "detail": "no slot records",
                "n_failed_slots": 0, "n_live_slots": 0,
                "providers_affected": []}
    failed, live = [], []
    for s in slots:
        (live if s.get("valid") and not s.get("refused") else failed).append(s)

    def _last_attempt(s):
        atts = s.get("attempts") or []
        return atts[-1] if atts else {}

    if not failed:
        return {"topology": TOPO_ALL_OK, "detail": "all slots live",
                "n_failed_slots": 0, "n_live_slots": len(live),
                "providers_affected": []}
    cats = {_last_attempt(s).get("failure_category", FAILURE_UNKNOWN)
            for s in failed}
    provs = {_last_attempt(s).get("provider_requested") or "unknown"
             for s in failed}
    detail = ("failed_slots=%d live_slots=%d categories=%s providers=%s"
              % (len(failed), len(live), sorted(cats), sorted(provs)))
    if cats <= {FAILURE_REFUSAL}:
        topo = TOPO_GENUINE_REFUSAL
    elif cats <= {FAILURE_PARSE, FAILURE_SCHEMA}:
        topo = TOPO_PARSE_CASCADE
    elif len(provs) == 1 and len(failed) >= 2:
        # every failure indicts the same provider: one correlated outage,
        # not len(failed) independent judge failures.
        topo = TOPO_PROVIDER_OUTAGE
    elif len(provs) >= 2 and cats & {FAILURE_CONN, FAILURE_TIMEOUT,
                                    FAILURE_HTTP_5XX}:
        # transport failures across providers: the shared path (herd
        # router / egress) is implicated, not the judges.
        topo = TOPO_SHARED_INFRA
    else:
        topo = TOPO_MIXED
    return {"topology": topo, "detail": detail,
            "n_failed_slots": len(failed), "n_live_slots": len(live),
            "providers_affected": sorted(provs),
            "failure_categories": sorted(cats)}


def _accepted_history():
    """Genuinely labeled accepted outcomes only (delegates to the
    provenance gate in calibration). Returns (rows, quarantined_count)."""
    return cal.labeled_history()


def shrunk_accuracy(k, n, pseudo_n=PRIOR_PSEUDO_N, prior_mean=PRIOR_MEAN):
    """Prior-shrinkage estimate of accepted-set accuracy. Explicit
    pseudo-counts — never synthetic labeled rows."""
    return (pseudo_n * prior_mean + k) / (pseudo_n + n)


def gate_operating_point(alpha=GATE_ALPHA):
    """The safety-vs-served-traffic operating point, computed from genuine
    labels only (arXiv:2609.22048: certified availability is a plannable
    deployment resource — this dict IS the plan)."""
    hist, quarantined = _accepted_history()
    n = len(hist)
    k = sum(1 for r in hist if r["correct"])
    lo, hi = cal.clopper_pearson(k, n, alpha)
    return {"safety_target": GATE_MIN_ACCURACY, "alpha": alpha,
            "history_n": n, "history_k": k,
            "cp_lo": lo, "cp_hi": hi,
            "shrunk_accuracy": shrunk_accuracy(k, n),
            "prior_pseudo_n": PRIOR_PSEUDO_N, "prior_mean": PRIOR_MEAN,
            "quarantined_rows": quarantined,
            "served_planned": bool(lo >= GATE_MIN_ACCURACY)}


def abstention_gate(posterior, struct_conf, alpha=GATE_ALPHA):
    """Finite-sample abstention gate (Judge/Retrieve/Abstain pattern).

    Emits only if the Clopper-Pearson LOWER bound on the genuinely labeled
    accepted set's accuracy stays above GATE_MIN_ACCURACY. No binary
    cold-start wall and no unanimity bypass: with n labels the gate
    certifies exactly what the exact-binomial bound supports; with n=0 the
    bound is 0 and the gate withholds (selective output). Below threshold
    -> ("escalate", reason), never emitted.
    """
    op = gate_operating_point(alpha)
    n, k, lo = op["history_n"], op["history_k"], op["cp_lo"]
    if op["served_planned"]:
        return ("emit",
                "CP lower bound on accepted accuracy %.3f >= %.2f "
                "(n=%d, k=%d, shrunk=%.3f, quarantined=%d)"
                % (lo, GATE_MIN_ACCURACY, n, k, op["shrunk_accuracy"],
                   op["quarantined_rows"]))
    return ("escalate",
            "CP lower bound %.3f < %.2f on %d labeled accepted "
            "(k=%d, shrunk=%.3f, quarantined=%d)"
            % (lo, GATE_MIN_ACCURACY, n, k, op["shrunk_accuracy"],
               op["quarantined_rows"]))


def check_canaries(judges, canaries=None):
    """PROCTOR-style canary pattern: seeded known-answer questions where a
    perfect-but-wrong pattern exposes gaming. Returns flags list; a flag is
    stake-and-slash evidence, not an auto-slash."""
    if canaries is None:
        if os.path.exists(CANARY_PATH):
            with open(CANARY_PATH) as f:
                canaries = json.load(f)
        else:
            canaries = []
    flags = []
    for j in judges:
        if not is_live(j):
            continue
        for c in canaries:
            ans = c.get("answer")
            # judge posterior on the canary is expected in j.canary_scores
            got = (j.__dict__.get("canary_scores") or {}).get(c.get("id"))
            if got is None or ans is None:
                continue
            wrong = (got >= 0.5) != bool(ans)
            if wrong and abs(got - (1.0 - ans)) < 0.05:
                # confidently wrong in exactly the anti-answer direction:
                # the gaming signature (perfect-but-wrong pattern)
                flags.append({"judge": j.judge_id, "canary": c.get("id"),
                              "pattern": "confident_anti_answer",
                              "posterior": got})
    return flags


def build_verdict(question_record, judges, prior=None, alpha=GATE_ALPHA):
    """Full verdict pipeline. Returns the verdict dict; status is one of
    'verdict' | 'escalate' | 'refused'. The engine owns every number."""
    if question_record.get("status") == "refused":
        return {"status": "refused", "question_id": None,
                "clarification_request":
                question_record.get("clarification_request")}
    prior = prior if prior is not None else question_record.get(
        "base_rate_prior", 0.5)
    loop = cal.CalibrationLoop()
    # apply deployed calibrators to raw judge posteriors
    calibrated = []
    for j in judges:
        raw = j.posterior
        p = loop.apply(j.judge_id, raw)
        nj = JudgePosterior(
            j.judge_id, p, j.cal_weight, j.reliability,
            j.verbal_conf, j.claims, refused=j.refused, valid=j.valid,
            failure_category=j.failure_category, provider=j.provider,
            model_family=j.model_family, attempts=j.attempts)
        calibrated.append(nj)
    post, contrib = pooled_posterior(prior, calibrated)
    feats = disagreement_features(calibrated)
    # bias-corrected reporting (judge-reporting math on the panel as an instrument)
    live = [j for j in calibrated if is_live(j)]
    agree = [1 if (j.posterior >= 0.5) == (post >= 0.5) else 0 for j in live]
    p_agree = sum(agree) / len(agree) if agree else 0.5
    n = len(agree)
    bc_point = cal.bias_corrected_point(p_agree, 0.9, 0.9)
    bc_lo, bc_hi = cal.bias_corrected_ci(p_agree, 0.9, 0.9, max(n, 1), 20, 20)
    gate = cal.RefusalGate()
    canary_flags = check_canaries(calibrated)
    gate.set("canary", "PASS" if not canary_flags else "FAIL",
             "%d gaming flags" % len(canary_flags))
    gate.set("panel_nonempty", "PASS" if live else "FAIL",
             "%d live judges" % len(live))
    decision, reason = abstention_gate(post, feats["confidence"], alpha)
    gate.set("abstention", "PASS" if decision == "emit" else "FAIL", reason)
    gate.set("drift", "NOT_CHECKED", "outer loop not yet run")
    op = gate_operating_point(alpha)
    slots = []
    for j in calibrated:
        atts = j.attempts or []
        last = atts[-1] if atts else {}
        slots.append({"slot": j.judge_id,
                      "served_by": last.get("slot_alias", j.judge_id),
                      "refused": j.refused, "valid": j.valid,
                      "failure_category": j.failure_category,
                      "provider": j.provider,
                      "attempts": atts})
    verdict = {
        "status": "verdict" if decision == "emit" else "escalate",
        "question_id": question_record.get("question_id"),
        "binary_question": question_record.get("binary_question"),
        "probability": post,
        "bias_corrected_agreement": bc_point,
        "agreement_ci": [bc_lo, bc_hi],
        "structural_confidence": feats,
        "prior": prior,
        "judge_contributions": contrib,
        "canary_flags": canary_flags,
        "gate": {"ok": gate.ok(), "failures": gate.failures(),
                 "limitations": gate.limitations_line()},
        "gate_reason": reason,
        "operating_point": op,
        "failure_topology": classify_failures(slots),
        "provider_diversity": {
            "n_providers": feats.get("n_providers", 0),
            "providers": feats.get("providers", []),
            "provider_collapse": True,
        },
        "judge_slots": slots,
        "ts": time.time(),
    }
    canon = json.dumps({k: verdict[k] for k in
                        ("question_id", "probability", "judge_contributions")},
                       sort_keys=True)
    verdict["verdict_sha256"] = hashlib.sha256(canon.encode()).hexdigest()[:16]
    return verdict


def record_verdict(verdict, path=VERDICT_LEDGER):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(verdict) + "\n")


def record_accepted_outcome(question_id, correct, path=None, source=None,
                            note=""):
    """Append a resolved outcome for the abstention gate's history.

    source is REQUIRED and must be in LABEL_SOURCES: only genuinely
    labeled outcomes (bench labels, human review, market settlement)
    become evidence. Anything else raises instead of silently writing
    an unlabeled row.
    """
    if source not in LABEL_SOURCES:
        raise ValueError(
            "record_accepted_outcome requires source in %s, got %r — "
            "unlabeled rows are quarantined, never written"
            % (sorted(LABEL_SOURCES), source))
    path = path or cal.HISTORY_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"question_id": question_id,
                            "correct": bool(correct),
                            "label_source": source,
                            "note": note,
                            "ts": time.time()}) + "\n")
