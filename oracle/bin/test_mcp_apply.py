#!/usr/bin/env python3
"""Unit tests for bin/mcp_apply.py (2026-10-19, osprey).

Covers: sandbox guard, edits-JSON parsing, and the local-fallback apply
path (Gatehouse pointed at a dead port forces the visible fallback).
The live Gatehouse read/edit round-trip is verified separately against
:25127; these tests must pass with no network at all.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/home/toxic/estate/ranch/squawk/oracle/bin")
import mcp_apply
from mcp_apply import (_check_path, McpError, parse_edits_json,
                       apply_change_set)

# ---- sandbox guard ----
assert _check_path("/home/toxic/estate/ranch/x.py") == \
    "/home/toxic/estate/ranch/x.py"
assert _check_path("/home/toxic/estate") == "/home/toxic/estate"
for bad in ["", "relative/path.py", "/etc/passwd",
            "/home/toxic/estate/../.ssh/id_rsa", "/tmp/evil.py",
            "/home/toxic/other/x.py", None, 123]:
    try:
        _check_path(bad)
        raise AssertionError("sandbox should reject: %r" % (bad,))
    except McpError:
        pass

# ---- edits-JSON parsing ----
edits, err = parse_edits_json(
    '{"edits": [{"path": "/a", "old": "x", "new": "y"}], "summary": "s"}')
assert err == "" and edits == [{"path": "/a", "old": "x", "new": "y"}], \
    (edits, err)
edits, err = parse_edits_json('[{"path": "/a", "old": "x", "new": "y"}]')
assert err == "" and len(edits) == 1
edits, err = parse_edits_json("no json here")
assert edits == [] and err
edits, err = parse_edits_json("")
assert edits == [] and err
edits, err = parse_edits_json('{"edits": [{"path": "/a"}]}')
assert edits == [] and err == ""  # malformed entries dropped, not fatal
edits, err = parse_edits_json('{"summary": "no edits key"}')
assert edits == [] and err

# ---- local fallback (dead Gatehouse -> visible fallback, same rules) ----
mcp_apply.GATEHOUSE_MCP_URL = "http://127.0.0.1:1/mcp"  # nothing listens
mcp_apply.GATEHOUSE_RPC_CUTOFF_S = 2
d = tempfile.mkdtemp()
mcp_apply.ALLOWED_ROOTS = (d,)
f = os.path.join(d, "f.txt")
open(f, "w").write("hello world\n")
ev = []
applied, failures = apply_change_set(
    [{"path": f, "old": "hello", "new": "goodbye"}], ev)
assert applied == 1 and not failures, (applied, failures, ev)
assert open(f).read() == "goodbye world\n"
assert any(e.get("fallback") == "local-apply" for e in ev), ev
assert any(e.get("via") == "local-fallback" and e.get("ok") for e in ev), ev
# anchor_not_unique fails visibly
open(f, "w").write("a a\n")
ev = []
applied, failures = apply_change_set(
    [{"path": f, "old": "a", "new": "b"}], ev)
assert applied == 0 and failures, (applied, failures)
assert failures[0]["error"] == "anchor_not_unique", failures[0]
assert open(f).read() == "a a\n"  # untouched
# anchor_missing fails visibly
ev = []
applied, failures = apply_change_set(
    [{"path": f, "old": "zzz", "new": "b"}], ev)
assert failures and failures[0]["error"] == "anchor_missing"
# empty change set is a no-op, not an error
ev = []
assert apply_change_set([], ev) == (0, [])
shutil.rmtree(d)
print("MCP_APPLY_UNIT_OK")
