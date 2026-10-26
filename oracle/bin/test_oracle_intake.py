#!/usr/bin/env python3
"""Unit tests for bin/oracle_intake.py (reconstructed from pyc)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, "/home/toxic/estate/ranch/squawk/oracle/bin")
from oracle_intake import (ROUTES, TAG_HINTS, KNOWN_BROKEN,
                           NO_CORRAL_MARKERS, _has_no_corral_marker,
                           _tags_for, triage)

led = tempfile.mktemp()
cases = [
    ("", "REJECT", "empty request"),
    ("!urgent fix prod", "DIRECT", "urgent flag"),
    ("petition to upgrade the model pool", "PETITION",
     "upgrade petition -> petition debate"),
    ("Should free models outrank paid models?", "DEBATE", "open question"),
    ("research the latency tail", "RESEARCH", "research need"),
    ("fix the broken health probe", "TASK", "biddable work"),
]
for text, route, reason in cases:
    d = triage({"from": "t", "text": text}, led)
    assert d["route"] == route, (text, d["route"], route)
    assert d["reason"] == reason, (text, d["reason"])
    assert d["event"] == "intake-decision"
    assert d["from"] == "t"
    assert isinstance(d["ts"], float)
    assert len(d["request"]) <= 500
d = triage({"from": "x", "text": "patch the buggy login page"}, led)
assert d["tags"] == ["code-fix"], d["tags"]
assert d["acceptance"].startswith("winner posts")
d2 = triage({"from": "x", "text": "hello world"}, led)
assert d2["tags"] == ["probe"]
assert _tags_for("fix bug and research docs") == ["code-fix", "research",
                                                  "docs"]
# request truncation
d3 = triage({"from": "x", "text": "y" * 900}, led)
assert len(d3["request"]) == 500
# default from
d4 = triage({"text": "probe the router"}, led)
assert d4["from"] == "?"
# hostile input never raises
triage({"from": "x", "text": None}, led)
triage({}, led)
# known-broken quarantine (2026-10-18): repair of a broken lane is never
# auctioned through that lane -- not even with !urgent
assert len(KNOWN_BROKEN) >= 1
dq = triage({"from": "osprey",
             "text": "repair the corral selectReviewTickets crash: "
                     "focuses is undefined (smthrs 0.35.0)"}, led)
assert dq["route"] == "REJECT", dq
assert "known-broken" in dq["reason"], dq["reason"]
assert dq["known_broken"] == "corral-render-selectReviewTickets", dq
dq2 = triage({"from": "osprey",
              "text": "!urgent fix selectReviewTickets focuses mismatch"},
             led)
assert dq2["route"] == "REJECT", dq2
assert dq2["known_broken"] == "corral-render-selectReviewTickets", dq2
# explicit no-corral marker (2026-10-19): execution-stack repairs run
# one-shot only -- DIRECT with no_corral=True, never the agentic lanes.
# The known-broken quarantine still wins when both match.
assert len(NO_CORRAL_MARKERS) == 3
assert _has_no_corral_marker("fix the bidder flap [no-corral]")
assert _has_no_corral_marker("!direct repair the retry loop")
assert _has_no_corral_marker("ROUTE:DIRECT patch the scheduler")
assert not _has_no_corral_marker("fix the broken health probe")
dn = triage({"from": "osprey",
             "text": "repair the bidder death-flap [no-corral]: "
                     "root-cause the restart loop"}, led)
assert dn["route"] == "DIRECT", dn
assert dn["no_corral"] is True, dn
assert "no-corral" in dn["reason"], dn["reason"]
dn2 = triage({"from": "x", "text": "!direct probe the queue depth"}, led)
assert dn2["route"] == "DIRECT" and dn2["no_corral"] is True, dn2
# plain !urgent stays DIRECT but without no_corral (corral lane kept)
du = triage({"from": "x", "text": "!urgent restart the tailer"}, led)
assert du["route"] == "DIRECT", du
assert "no_corral" not in du, du
# marker cannot hurry a known-broken repair: quarantine runs first
dq4 = triage({"from": "osprey",
              "text": "[no-corral] repair selectReviewTickets: "
                      "focuses undefined"}, led)
assert dq4["route"] == "REJECT", dq4
assert dq4["known_broken"] == "corral-render-selectReviewTickets", dq4
# one keyword alone does not quarantine
dq3 = triage({"from": "x", "text": "check the focuses logic in the dashboard"},
             led)
assert not (dq3["route"] == "REJECT"
            and "known-broken" in dq3["reason"]), dq3
# route:mcp override (2026-10-19): explicit MCP-apply marker -> DIRECT
# with mcp_apply=True and no_corral=True (first-class apply, override)
from oracle_intake import MCP_APPLY_MARKERS, _has_mcp_apply_marker
assert len(MCP_APPLY_MARKERS) == 3
assert _has_mcp_apply_marker("fix the login bug route:mcp")
assert _has_mcp_apply_marker("patch it [mcp-apply]")
assert _has_mcp_apply_marker("!mcp repair the scheduler")
assert not _has_mcp_apply_marker("fix the broken health probe")
dm = triage({"from": "x", "text": "fix the login bug route:mcp"}, led)
assert dm["route"] == "DIRECT", dm
assert dm["mcp_apply"] is True, dm
assert dm["no_corral"] is True, dm
# marker cannot hurry a known-broken repair either: quarantine first
dq5 = triage({"from": "osprey",
              "text": "route:mcp repair selectReviewTickets: "
                      "focuses undefined"}, led)
assert dq5["route"] == "REJECT", dq5
assert dq5["known_broken"] == "corral-render-selectReviewTickets", dq5
rows = [json.loads(line) for line in open(led)]
assert all(r["event"] == "intake-decision" for r in rows)
assert len(rows) == 21
os.unlink(led)
print("INTAKE_UNIT_OK routes=%s hints=%s" % (ROUTES, sorted(TAG_HINTS)))
