#!/usr/bin/env python3
"""Evidence layer: designed information asymmetry + atomic claims.

Two mechanisms from the research, fused:

1. Designed asymmetry (InfoDelphi, arXiv:2607.01661): identical evidence
   makes deliberation collapse into herding. Each judge gets a shared
   public core + a DISJOINT private subset, routed relevance-aware. Judges
   with exclusive knowledge can only influence others through the engine.

2. Atomic-claim Bayesian engine (predict-raven, MIT): one claim = one
   update; multiple sources on the same claim only adjust verification
   quality; every cited URL reconciled against the actual retrieval trace
   (fabrication guard); per-round continuity invariant.

Evidence item: {"id", "text", "relevance" (0..1), "source", "url",
                 "credibility" ("low"|"medium"|"high")}.
Claim: {"claim_id","text","stance","llr","cluster_id","rationale","urls",
        "verified","credibility","revision_of"}.
"""
import hashlib
import time

import bayes


def partition_evidence(items, n_judges, public_frac=0.4):
    """Split evidence into a shared public core + disjoint private subsets.

    items: list of evidence dicts with "relevance". Top public_frac by
    relevance become the public core; the remainder are dealt round-robin
    in relevance order so every judge gets a disjoint private set of
    comparable total relevance. Deterministic (sorted, no RNG).
    """
    if n_judges < 1:
        raise ValueError("n_judges >= 1")
    ranked = sorted(items, key=lambda e: (-e.get("relevance", 0.0),
                                          e.get("id", "")))
    n_pub = max(1 if ranked else 0, int(len(ranked) * public_frac))
    public = ranked[:n_pub]
    private_pool = ranked[n_pub:]
    privates = [[] for _ in range(n_judges)]
    for k, item in enumerate(private_pool):
        privates[k % n_judges].append(item)
    return {"public": public,
            "private": privates,
            "stats": {"n_public": len(public),
                      "n_private": [len(p) for p in privates],
                      "asymmetry": 1.0 - (len(public) / max(1, len(ranked))) }}


def verify_claim_urls(claim, retrieval_trace):
    """Fabrication guard: every cited URL must appear in the real retrieval
    trace (the set of URLs the judge actually fetched). Returns the claim
    with verified=True/False. Unverified claims are NOT dropped — they are
    soft-clamped by the engine (trace capture can false-negative)."""
    trace = set(retrieval_trace or [])
    urls = claim.get("urls") or []
    claim = dict(claim)
    claim["verified"] = bool(urls) and all(u in trace for u in urls)
    return claim


def apply_claims(prior, claims, prior_cluster_counts=None, retrieval_trace=None):
    """Run atomic claims through the Bayesian engine with all guards.

    Order of guards per claim: stance-signed LLR -> unverified soft-clamp
    -> credibility cap -> reflection clamp (if revision_of) -> cluster
    discounting. Returns (posterior, steps, report)."""
    prior_cluster_counts = prior_cluster_counts or {}
    eff = []
    guarded = []
    for c in claims:
        c = verify_claim_urls(c, retrieval_trace)
        llr = bayes.effective_llr(c.get("stance"), c.get("llr", 0.0))
        guards = []
        if not c["verified"]:
            llr = bayes.clamp_unverified(llr)
            guards.append("unverified_soft_clamp")
        capped = bayes.credibility_cap(c.get("credibility", "medium"), llr)
        if capped != llr:
            guards.append("credibility_cap")
        llr = capped
        if c.get("revision_of"):
            r = bayes.clamp_reflection(llr)
            if r != llr:
                guards.append("reflection_clamp")
            llr = r
        eff.append(llr)
        guarded.append((c, guards))
    factors = bayes.cluster_factors(
        [c.get("cluster_id", "") for c, _ in guarded], eff,
        prior_cluster_counts)
    final_llrs = []
    for (c, guards), f, l in zip(guarded, factors, eff):
        fl = l * f
        if f < 1.0:
            guards.append("cluster_discount_x%.2f" % f)
        final_llrs.append(fl)
    post, steps, pinned = bayes.apply_llrs(prior, final_llrs)
    for step, (c, guards) in zip(steps, guarded):
        step["claim_id"] = c.get("claim_id")
        step["guards"] = guards
        step["verified"] = c["verified"]
    new_counts = dict(prior_cluster_counts)
    for c, _ in guarded:
        cid = (c.get("cluster_id") or "").strip()
        if cid:
            new_counts[cid] = new_counts.get(cid, 0) + 1
    report = {
        "posterior": post, "pinned": pinned,
        "confirmation_ratio": bayes.confirmation_ratio(prior, final_llrs),
        "n_claims": len(claims),
        "n_unverified": sum(1 for c, _ in guarded if not c["verified"]),
        "cluster_counts": new_counts,
    }
    return post, steps, report


def round_update(prev_posterior, claims, ledger_state, retrieval_trace=None):
    """Continuity invariant: round n prior = round n-1 posterior.
    ledger_state: {"cluster_counts": {...}} persisted across rounds."""
    counts = (ledger_state or {}).get("cluster_counts", {})
    post, steps, report = apply_claims(prev_posterior, claims, counts,
                                       retrieval_trace)
    return post, steps, report


def claim_id(text, source=""):
    return hashlib.sha256((text + "|" + source).encode()).hexdigest()[:12]


def summarize_evidence_for_judge(partition, judge_idx):
    """Render one judge's asymmetric view: public core + its private set."""
    pub = partition["public"]
    priv = partition["private"][judge_idx]
    lines = ["SHARED PUBLIC EVIDENCE (%d items):" % len(pub)]
    for e in pub:
        lines.append("- [%s] %s (src: %s, rel=%.2f)" %
                     (e.get("id"), e.get("text"), e.get("source"),
                      e.get("relevance", 0)))
    lines.append("YOUR PRIVATE EVIDENCE (%d items, exclusive to you):" % len(priv))
    for e in priv:
        lines.append("- [%s] %s (src: %s, rel=%.2f)" %
                     (e.get("id"), e.get("text"), e.get("source"),
                      e.get("relevance", 0)))
    lines.append("Do not assume other judges saw your private evidence.")
    return "\n".join(lines)
