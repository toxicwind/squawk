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


def _tags_for(text):
    tl = text.lower()
    tags = [t for t, kws in TAG_HINTS.items() if any(k in tl for k in kws)]
    return tags or ["probe"]


def triage(request, ledger_path):
    """Classify one intake request; append the decision to the ledger.

    request: {"from": str, "text": str}. Returns the decision dict.
    Never raises on hostile input (empty/garbage -> REJECT).
    """
    text = (request.get("text") or "").strip()
    frm = request.get("from", "?")
    if not text:
        route, reason = "REJECT", "empty request"
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
    if route == "TASK":
        decision["tags"] = _tags_for(text)
        decision["acceptance"] = \
            "winner posts a result payload; oracle verifies success flag"
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision) + "\n")
    return decision
