"""Oracle intake: front-door triage for all work requests.

Six routes: TASK / DEBATE / RESEARCH / PETITION / DIRECT / REJECT.
Decisions are append-only records in the market ledger; intake never
mutates tasks. Wired into oracle_loop behind ORACLE_INTAKE=1 (v0 baseline:
keyword heuristics; the oracle refines them through petition/debate per
the agent-governance commitment).
"""
import json
import time

ROUTES = ("TASK", "DEBATE", "RESEARCH", "PETITION", "DIRECT", "REJECT")

TAG_HINTS = {
    "code-fix": ("fix", "bug", "broken", "repair", "patch"),
    "probe": ("probe", "health", "check", "ping", "smoke"),
    "research": ("research", "investigate", "survey", "audit"),
    "docs": ("doc", "readme", "writeup", "document"),
}

# Known-broken components (2026-10-18): intake signatures that must never be
# auctioned into the market's agentic lanes, because the lane itself is the
# broken component. Repair of these components happens in a direct lane with
# an explicit brief -- never through the market. Entries are
# (signature_id, required_keywords); every keyword must appear in the
# lowercased intake text for the signature to match. The quarantine check
# runs before every other route rule (including !urgent): a broken lane
# cannot be hurried.
KNOWN_BROKEN = (
    # smthrs 0.35.0 selector API mismatch: the corral/super-ralph workflow
    # renderer throws on undefined `focuses` at selectReviewTickets. Both
    # agentic execution paths die on it, so auctioning its repair through
    # the market only burns bidder runs (intakes 2617, 2628, 2638, 2648,
    # 2658, 2690 all died this way; bonds returned, no money moved).
    ("corral-render-selectReviewTickets",
     ("selectreviewtickets", "focuses")),
)


def _tags_for(text):
    tl = text.lower()
    tags = [t for t, kws in TAG_HINTS.items() if any(k in tl for k in kws)]
    return tags or ["probe"]


def _known_broken_sig(text):
    """Return the known-broken signature id matching text, or None."""
    tl = (text or "").lower()
    for sig, kws in KNOWN_BROKEN:
        if all(k in tl for k in kws):
            return sig
    return None


def triage(request, ledger_path):
    """Classify one intake request; append the decision to the ledger.

    request: {"from": str, "text": str}. Returns the decision dict.
    Never raises on hostile input (empty/garbage -> REJECT).
    """
    text = (request.get("text") or "").strip()
    frm = request.get("from", "?")
    sig = _known_broken_sig(text)
    if not text:
        route, reason = "REJECT", "empty request"
    elif sig:
        route, reason = (
            "REJECT",
            "known-broken component %s: repair runs in a direct lane, "
            "never auctioned through the broken lane" % sig,
        )
    elif text.startswith("!urgent"):
        route, reason = "DIRECT", "urgent flag"
    elif "petition" in text.lower() and "upgrade" in text.lower():
        route, reason = "PETITION", "upgrade petition -> petition debate"
    elif text.rstrip().endswith("?"):
        route, reason = "DEBATE", "open question"
    elif any(k in text.lower()
             for k in ("research", "investigate", "survey", "audit")):
        route, reason = "RESEARCH", "research need"
    else:
        route, reason = "TASK", "biddable work"
    assert route in ROUTES
    decision = {
        "event": "intake-decision",
        "ts": time.time(),
        "from": frm,
        "route": route,
        "reason": reason,
        "request": text[:500],
    }
    if sig:
        decision["known_broken"] = sig
    if route == "TASK":
        decision["tags"] = _tags_for(text)
        decision["acceptance"] = \
            "winner posts a result payload; oracle verifies success flag"
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision) + "\n")
    return decision
