#!/usr/bin/env python3
"""Belief-to-trade firewall (Raven lesson, arXiv:2607.03015).

A calibrated probability is NOT a trading result. Between the verdict and
any bid/stake sits this sizing layer:

  * Kelly-style sizing: f* = (b*p - q)/b with fractional Kelly and a hard
    cap — the verdict probability never directly sets the stake.
  * Wang Transform fair-value engine (oracle3, Apache-2.0, calibrated on
    291,309 resolved contracts): p_mkt = Phi(Phi^{-1}(p*) + lambda),
    lambda_hat = 0.183 global; hierarchical covariate form
    lambda_i = 0.259 - 0.072*ln(1+V) + 0.143*ln(1+D) - 0.477*|p-0.5|
    corrects the favorite-longshot bias (a true 50% trades ~57c).
  * Probability-axiom invariant strategies (oracle3): exclusivity,
    event-sum unity, implication monotonicity — violations are signals,
    and a violation on a verdict's question set escalates it to DEBATE.

See docs/BORROWS.md for attribution.
"""
import math

import calibration as cal  # norm_cdf / norm_ppf

# Kelly defaults (documented in docs/oracle-core.md).
KELLY_FRACTION = 0.25   # fractional Kelly: quarter-Kelly is the sane default
KELLY_CAP = 0.10        # never stake more than 10% of bankroll on one verdict
MIN_EDGE = 0.02         # no bet without at least 2pp of edge vs fair value


def kelly_fraction(p, price, fraction=KELLY_FRACTION, cap=KELLY_CAP):
    """f* = (b*p - q)/b where b = (1-price)/price net odds, q = 1-p.
    Returns 0 when there is no edge. p = our probability, price = market."""
    if not 0.0 < price < 1.0 or not 0.0 <= p <= 1.0:
        return 0.0
    b = (1.0 - price) / price
    q = 1.0 - p
    f = (b * p - q) / b if b > 0 else 0.0
    f = max(0.0, f) * fraction
    return min(cap, f)


def wang_lambda(volume=None, days_to_expiry=None, p=None):
    """Hierarchical covariate model; falls back to the global 0.183."""
    if volume is None or days_to_expiry is None or p is None:
        return 0.183
    return (0.259 - 0.072 * math.log1p(volume)
            + 0.143 * math.log1p(days_to_expiry)
            - 0.477 * abs(p - 0.5))


def wang_fair_value(p_star, volume=None, days_to_expiry=None):
    """p_mkt = Phi(Phi^{-1}(p*) + lambda). Reference price for binary
    questions; the favorite-longshot correction lives in lambda."""
    lam = wang_lambda(volume, days_to_expiry, p_star)
    pc = min(1.0 - 1e-9, max(1e-9, p_star))
    return cal.norm_cdf(cal.norm_ppf(pc) + lam)


def size_stake(verdict_p, market_price, bankroll, volume=None,
               days_to_expiry=None):
    """Full firewall: fair-value reference -> edge check -> Kelly sizing.
    Returns {"action","stake","edge","fair_value","kelly_f"}.
    action is one of bet_yes / bet_no / no_bet. Symmetric for NO via 1-p."""
    fair = wang_fair_value(verdict_p, volume, days_to_expiry)
    edge_yes = verdict_p - market_price
    edge_no = (1 - verdict_p) - (1 - market_price)
    if edge_yes >= MIN_EDGE and edge_yes >= edge_no:
        f = kelly_fraction(verdict_p, market_price)
        return {"action": "bet_yes", "stake": f * bankroll, "edge": edge_yes,
                "fair_value": fair, "kelly_f": f}
    if edge_no >= MIN_EDGE:
        f = kelly_fraction(1 - verdict_p, 1 - market_price)
        return {"action": "bet_no", "stake": f * bankroll, "edge": edge_no,
                "fair_value": 1 - fair, "kelly_f": f}
    return {"action": "no_bet", "stake": 0.0,
            "edge": max(edge_yes, edge_no), "fair_value": fair, "kelly_f": 0.0}


def invariant_check(questions, tol=0.02):
    """Probability-axiom invariant strategies (oracle3 pattern).

    questions: list of {"id", "p", "group" (exclusivity set id or None),
                        "implies" (id this question's YES implies), ...}.
    Checks: exclusivity (sum of P over an exclusive group <= 1+tol),
    event-sum unity (a "partition" group sums to 1 within tol),
    implication monotonicity (P(A) <= P(B)+tol when A implies B).
    Returns list of violation dicts (empty = clean).
    """
    by_id = {q["id"]: q for q in questions}
    violations = []
    groups = {}
    for q in questions:
        g = q.get("group")
        if g:
            groups.setdefault(g, []).append(q)
    for g, qs in groups.items():
        kind = qs[0].get("group_kind", "exclusive")
        s = sum(q["p"] for q in qs)
        if kind == "exclusive" and s > 1.0 + tol:
            violations.append({"invariant": "exclusivity", "group": g,
                               "sum": s, "detail": "sum P > 1"})
        elif kind == "partition" and abs(s - 1.0) > tol:
            violations.append({"invariant": "event_sum_unity", "group": g,
                               "sum": s, "detail": "partition sum != 1"})
    for q in questions:
        tgt = q.get("implies")
        if tgt and tgt in by_id:
            if q["p"] > by_id[tgt]["p"] + tol:
                violations.append({"invariant": "implication_monotonicity",
                                   "from": q["id"], "to": tgt,
                                   "p_from": q["p"],
                                   "p_to": by_id[tgt]["p"]})
    return violations
