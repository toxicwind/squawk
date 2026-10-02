#!/usr/bin/env python3
"""Fail-closed question framing (Round 0).

Every Oracle question is normalized to: binary question + explicit
resolution criteria + resolution date + settlement source + base-rate prior.
Vague questions are REFUSED with a clarification request — never answered
with false precision. (Borrow: predict-raven packages/forecast-engine
framing.ts, MIT; see docs/BORROWS.md.)

The framed record is what judges see and what the engine signs into the
verdict. Garbage in here is the one failure the engine cannot fix
downstream, so this layer fails closed by design.
"""
import hashlib
import re
import time
from datetime import datetime, timezone

# Base-rate priors for common question shapes. These are starting points the
# evidence layer must move — not answers. Documented, versioned, auditable.
BASE_RATES = {
    "election": 0.50,
    "price_above": 0.50,      # symmetric threshold moves
    "rain": 0.30,
    "sports": 0.50,
    "launch_on_time": 0.35,   # launches slip more often than not
    "default": 0.50,
}

DATE_RES = [
    (re.compile(r"\bby\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})"), "%B %d %Y"),
    (re.compile(r"\bby\s+(\d{4}-\d{2}-\d{2})"), "%Y-%m-%d"),
    (re.compile(r"\bbefore\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})"), "%B %d %Y"),
    (re.compile(r"\bin\s+(Q[1-4]\s+\d{4})"), None),
    (re.compile(r"\bby\s+end\s+of\s+(\d{4})"), None),
]

SOURCE_HINTS = [
    (re.compile(r"\b(polymarket|kalshi|predictit)\b", re.I), "prediction-market"),
    (re.compile(r"\b(fed|fomc|bls|cpi|payrolls)\b", re.I), "official-release"),
    (re.compile(r"\$\b[A-Z]{1,5}\b"), "market-price"),
    (re.compile(r"\b(election|vote|poll)\b", re.I), "election-result"),
    (re.compile(r"\b(rain|temperature|hurricane|weather)\b", re.I), "weather-service"),
]

# Anchor patterns for the vagueness guard: a resolvable question must name
# something concrete -- a date/deadline, a number, a proper noun, or a
# quoted span. Bare demonstratives ("Will this work?") name nothing.
_ANCHOR_RES = [
    re.compile(r"\b(today|tomorrow|tonight|this\s+(week|month|year)|"
               r"next\s+(week|month|year))\b", re.I),
    re.compile(r"\d"),
    # proper noun, not sentence-initial:
    re.compile(r"(?<=[a-z]\s)[A-Z][a-z]+"),
    re.compile(r"[\"\u201c\u2018]([^\"\u201c\u2018]{2,})[\"\u201c\u2018]"),
]

_DIGIT_RES = re.compile(r"\d")

# Future-oriented questions must be resolvable as framed: they need a
# DEADLINE (when the world gets checked) and a RESOLUTION anchor (what
# counts as YES -- a numeric threshold, a quoted proposition, or an
# inherently binary observable event). Without both, the question is
# refused rather than answered with false precision. Historical/present
# questions keep the single-anchor rule -- "Did Apollo 11 land humans on
# the Moon in 1969?" is already fully specified by its anchors.
_FUTURE_RES = [
    re.compile(r"\bwill\b", re.I),
    re.compile(r"\bgoing\s+to\b", re.I),
]
_PAST_LED_RES = re.compile(r"^\s*(did|was|were|has|have|had)\b", re.I)
_DEADLINE_RES = [
    re.compile(r"\b(today|tomorrow|tonight|this\s+(week|month|year)|"
               r"next\s+(week|month|year))\b", re.I),
    re.compile(r"\bby\s+\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\bby\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\b"),
    re.compile(r"\bbefore\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\b"),
    re.compile(r"\bin\s+Q[1-4]\s+\d{4}\b", re.I),
    re.compile(r"\bby\s+end\s+of\s+\d{4}\b", re.I),
    re.compile(r"\b(19|20)\d{2}\b"),  # explicit year as deadline
]
# Inherently binary, observable event verbs. Intentionally narrow: an
# unknown verb fails closed (refused with a clarification request).
_BINARY_EVENT_RES = re.compile(
    r"\b(rise|set|occur|happen|take\s+place|launch|land|win|lose|"
    r"pass|fail|rain|snow|erupt|collapse|default|resign|die|"
    r"eclipse)\b", re.I)


REFUSE_PATTERNS = [
    (re.compile(r"^\s*(hi|hello|hey|yo)\b", re.I), "greeting, not a question"),
    (re.compile(r"^\s*$"), "empty question"),
]


def _extract_date(text):
    for rx, fmt in DATE_RES:
        m = rx.search(text)
        if not m:
            continue
        raw = m.group(1).replace(",", "")
        if fmt is None:
            return raw  # quarter/year kept as-is
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return raw
    return None


def _settlement_source(text):
    for rx, name in SOURCE_HINTS:
        if rx.search(text):
            return name
    return "unspecified"


def _question_shape(text):
    tl = text.lower()
    if re.search(r"\b(election|win the|president|senate)\b", tl):
        return "election"
    if re.search(r"\b(above|below|exceed|under)\b.*\$|\$\s*\d", tl):
        return "price_above"
    if re.search(r"\b(rain|snow)\b", tl):
        return "rain"
    if re.search(r"\b(launch|release|ship)\b", tl):
        return "launch_on_time"
    if re.search(r"\b(game|match|beat|playoff|championship)\b", tl):
        return "sports"
    return "default"


def frame_question(text, now=None):
    """Normalize a raw ask into a framed question record.

    Returns dict with status "framed" or "refused". Refusals carry a
    clarification_request the caller should surface verbatim.
    """
    now = now or time.time()
    raw = (text or "").strip()
    for rx, why in REFUSE_PATTERNS:
        if rx.search(raw):
            return {"status": "refused", "refusal_reason": why,
                    "clarification_request":
                    "I need a concrete yes/no question to resolve. "
                    "What exactly should happen, by when, and how would we "
                    "check the outcome?",
                    "raw": raw}
    if len(raw) < 12:
        return {"status": "refused", "refusal_reason": "too short to frame",
                "clarification_request":
                "That is too short to resolve as a yes/no question. "
                "Please state the full question, e.g. 'Will X happen by <date>?'",
                "raw": raw}
    if not raw.rstrip().endswith("?") and not re.search(
            r"\b(will|is|are|does|did|has|have|can)\b", raw, re.I):
        return {"status": "refused", "refusal_reason": "not a resolvable question",
                "clarification_request":
                "I resolve yes/no questions. Please rephrase as one, e.g. "
                "'Will <event> happen by <date>?'",
                "raw": raw}

    # Vague/unresolvable guard (fail-closed, 2026-09-20; future rule
    # hardened 2026-09-20): a question with no resolvable referent is
    # refused, never answered with false precision.
    is_future = (any(rx.search(raw) for rx in _FUTURE_RES)
                 and not _PAST_LED_RES.search(raw))
    if is_future:
        # Future questions are bets on the world: they need a deadline
        # (when the world gets checked) AND a resolution anchor (what
        # counts as YES). A bare proper noun is not a resolution --
        # "Will Bitcoin go up?" names a thing but no checkable outcome.
        has_deadline = any(rx.search(raw) for rx in _DEADLINE_RES)
        has_resolution = (_DIGIT_RES.search(raw)
                          or _ANCHOR_RES[3].search(raw)
                          or _BINARY_EVENT_RES.search(raw))
        if not (has_deadline and has_resolution):
            missing = " and ".join(
                name for name, ok in
                (("a resolution date", has_deadline),
                 ("a resolvable event or threshold", has_resolution))
                if not ok)
            return {"status": "refused",
                    "refusal_reason": "future question missing " + missing,
                    "clarification_request":
                    "I can't resolve that as a yes/no bet yet -- it's "
                    "missing %s. Please state what should happen and by "
                    "when, e.g. 'Will <event> happen by <date>?'." % missing,
                    "raw": raw}
    elif not any(rx.search(raw) for rx in _ANCHOR_RES):
        return {"status": "refused", "refusal_reason": "too vague to resolve",
                "clarification_request":
                "That names nothing concrete to resolve. Please state what "
                "should happen, to what or whom, and by when -- e.g. "
                "'Will <event> happen by <date>?'",
                "raw": raw}

    resolution_date = _extract_date(raw)
    shape = _question_shape(raw)
    record = {
        "status": "framed",
        "binary_question": raw if raw.rstrip().endswith("?") else raw + "?",
        "resolution_criteria": (
            "YES iff the stated event observably occurs on or before %s; "
            "NO otherwise. Ambiguous outcomes resolve NO."
            % (resolution_date or "the resolution date")),
        "resolution_date": resolution_date,
        "settlement_source": _settlement_source(raw),
        "base_rate_prior": BASE_RATES[shape],
        "question_shape": shape,
        "framed_ts": now,
    }
    if resolution_date is None:
        record["limitations"] = ("no explicit resolution date found; "
                                 "verdict is date-agnostic")
    canon = "|".join(str(record[k]) for k in
                     ("binary_question", "resolution_criteria",
                      "resolution_date", "settlement_source"))
    record["question_id"] = hashlib.sha256(canon.encode()).hexdigest()[:16]
    return record


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(frame_question(" ".join(sys.argv[1:])), indent=2))
