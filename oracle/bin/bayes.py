#!/usr/bin/env python3
"""Bayesian log-odds engine — the math under the Oracle's deterministic core.

Python port of bayes.ts from Alchemist-X/predict-raven
(https://github.com/Alchemist-X/predict-raven, MIT License,
Copyright (c) 2026 Alchemist-X). Adapted to Python with the invariants
intact; see docs/BORROWS.md for attribution.

Invariants (engine owns the number):
  * Work in log-odds space: prior -> logit, each claim adds a signed LLR,
    posterior read back as probability. Additive => per-source attribution.
  * One atomic claim = one update. Extra sources on the same claim only
    adjust verification quality (cluster discounting kills page-counting).
  * Fabrication guard: a claim whose URL never appeared in the real
    retrieval trace is soft-clamped to near-zero influence (not dropped —
    the trace capture can false-negative).
  * Credibility caps: a low-credibility source can never outweigh a
    high-quality one no matter what strength the judge claims.
  * Reflection (revising a prior claim) is clamped tighter than fresh
    evidence: a round can nudge, never violently re-litigate (anti-oscillation).
  * Cluster discounting is ledger-aware: priorCounts from previous rounds
    shift every rank, so a re-counted story starts at decay^k.
  * Probability is never pinned to 0/1; the `pinned` flag reports when the
    unclamped posterior crossed the expressible bound (a floor-pinned 1.0%
    is NOT a converged estimate).
"""
import math

EPS = 1e-6

MAX_ABS_LLR = 2.0        # per-claim clamp (nats)
PROB_FLOOR = 0.01
PROB_CEIL = 0.99
UNVERIFIED_MAX_LLR = 0.2  # fabrication-guard soft clamp
REFLECTION_MAX_LLR = 1.0
CLUSTER_DECAY = 0.5
CREDIBILITY_MAX_LLR = {"low": 0.25, "medium": 0.8, "high": MAX_ABS_LLR}


def clamp(x, lo, hi):
    return min(hi, max(lo, x))


def logit(p):
    c = clamp(p, EPS, 1.0 - EPS)
    return math.log(c / (1.0 - c))


def inv_logit(l):
    return 1.0 / (1.0 + math.exp(-l))


def effective_llr(stance, raw_llr):
    """(stance, magnitude) -> signed effective LLR. Sign comes from stance so a
    judge that mislabels the sign cannot push the probability the wrong way."""
    try:
        mag = abs(float(raw_llr))
    except (TypeError, ValueError):
        mag = 0.0
    mag = clamp(mag, 0.0, MAX_ABS_LLR)
    if stance == "supports_yes":
        return mag
    if stance == "supports_no":
        return -mag
    return 0.0  # neutral


def clamp_unverified(llr):
    mag = min(abs(llr), UNVERIFIED_MAX_LLR)
    return math.copysign(mag, llr) if llr else 0.0


def credibility_cap(credibility, llr):
    cap = CREDIBILITY_MAX_LLR.get(credibility, CREDIBILITY_MAX_LLR["medium"])
    return math.copysign(min(abs(llr), cap), llr) if llr else 0.0


def clamp_reflection(llr):
    try:
        v = float(llr)
    except (TypeError, ValueError):
        v = 0.0
    if not math.isfinite(v):
        v = 0.0
    mag = min(abs(v), REFLECTION_MAX_LLR)
    return math.copysign(mag, v) if v else 0.0


def cluster_factors(cluster_ids, llrs, prior_counts=None):
    """Independence-aware aggregation. Within a cluster the strongest source
    keeps full weight; additional same-cluster sources are geometrically
    damped (decay^rank). prior_counts maps cluster_id -> already-counted
    entries from previous rounds; rank starts after those."""
    groups = {}
    for i, cid in enumerate(cluster_ids):
        key = cid.strip() if cid and cid.strip() else "__solo_%d" % i
        groups.setdefault(key, []).append(i)
    factors = [1.0] * len(cluster_ids)
    for key, idxs in groups.items():
        offset = (prior_counts or {}).get(key, 0)
        if len(idxs) <= 1 and offset == 0:
            continue
        ranked = sorted(idxs, key=lambda j: abs(llrs[j] if j < len(llrs) else 0.0),
                        reverse=True)
        for rank, idx in enumerate(ranked):
            factors[idx] = CLUSTER_DECAY ** (rank + offset)
    return factors


def confirmation_ratio(prior_prob, llrs):
    """Fraction of |LLR| mass confirming the prior lean. A ratio near 1.0
    round after round is a confirmation-bias ratchet. None when no lean."""
    lean = 1 if prior_prob > 0.5 else (-1 if prior_prob < 0.5 else 0)
    if lean == 0:
        return None
    confirming = total = 0.0
    for l in llrs:
        m = abs(l)
        total += m
        if (l > 0) - (l < 0) == lean:
            confirming += m
    return confirming / total if total > 0 else None


def apply_llrs(prior_prob, llrs):
    """Thread LLRs through the prior. Returns (post, steps, pinned) where
    steps give per-source attribution (prob_before, prob_after, delta_pp)."""
    lo = logit(prior_prob)
    steps = []
    for llr in llrs:
        before = clamp(inv_logit(lo), PROB_FLOOR, PROB_CEIL)
        lo += llr
        after = clamp(inv_logit(lo), PROB_FLOOR, PROB_CEIL)
        steps.append({"prob_before": before, "prob_after": after,
                      "delta_pp": (after - before) * 100.0, "llr": llr})
    raw = inv_logit(lo)
    pinned = "floor" if raw < PROB_FLOOR else ("ceil" if raw > PROB_CEIL else None)
    return clamp(raw, PROB_FLOOR, PROB_CEIL), steps, pinned


def credible_band(prob, n_sources, confidence="medium"):
    """Crude-but-honest uncertainty cue: narrows with independent sources.
    NOT a calibrated interval — the abstention gate uses Clopper-Pearson."""
    factor = {"high": 0.6, "medium": 0.85, "low": 1.1}.get(confidence, 0.85)
    half = (0.18 * factor) / math.sqrt(1 + n_sources)
    return (clamp(prob - half, PROB_FLOOR, PROB_CEIL),
            clamp(prob + half, PROB_FLOOR, PROB_CEIL))
