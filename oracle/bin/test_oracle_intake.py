#!/usr/bin/env python3
"""Unit tests for bin/oracle_intake.py (reconstructed from pyc)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, "/home/toxic/estate/projects/range/ranch/oracle/bin")
from oracle_intake import triage, _tags_for, ROUTES, TAG_HINTS

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
rows = [json.loads(line) for line in open(led)]
assert all(r["event"] == "intake-decision" for r in rows)
assert len(rows) == 12
os.unlink(led)
print("INTAKE_UNIT_OK routes=%s hints=%s" % (ROUTES, sorted(TAG_HINTS)))
