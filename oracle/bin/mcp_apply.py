#!/usr/bin/env python3
"""First-class MCP apply for the oracle market (2026-10-19, osprey).

On oracle approval, code changes are applied DIRECTLY to the repo through
the yote Thresher MCP proxy (:25127) -- anchored read -> edit -> verify.
Every MCP tool call is recorded as task evidence. This is the market's
native apply mechanism, not an opt-in lane.

Why this exists (Chris 2026-10-19): the market generated change text but
had zero MCP client wiring -- `ffs grep mcp` across oracle/bin returned
nothing. Winners now apply through Thresher by default.

Failure degrades VISIBLY, never silently: if Thresher is unreachable or
a tool call errors, the same anchored edits are applied with local file
IO and the evidence records mcp_unavailable + local fallback. A task is
never failed by the apply transport alone when the edits themselves are
sound.
"""
import json
import os
import urllib.request
from pathlib import Path

# ---- open configuration (not buried constants) ----
THRESHER_MCP_URL = "http://127.0.0.1:25127/mcp"
THRESHER_RPC_CUTOFF_S = 60
# Edits are sandboxed under these roots. Absolute paths only; anything
# escaping via .. is rejected before any tool call.
ALLOWED_ROOTS = ("/home/toxic/estate",)
READ_TOOL = "filesystem:read_text_file"
EDIT_TOOL = "filesystem:edit_file"  # via call_tool_destructive
MAX_EDITS_PER_TASK = 25


class McpError(Exception):
    """Thresher unreachable, tool errored, or response unparseable."""


def _unwrap(res):
    """Pull the text payload out of a Thresher tools/call response."""
    try:
        return res["result"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise McpError("unexpected thresher response: %s"
                       % json.dumps(res)[:300])


class ThresherMCP:
    """Minimal Thresher JSON-RPC client (yote-local, no credentials --
    the proxy trusts localhost; the market runs on yote)."""

    def __init__(self, base_url=None):
        # Resolve at call time, not def time, so tests/ops can repoint
        # THRESHER_MCP_URL without reimporting.
        self.base_url = base_url or THRESHER_MCP_URL
        self.sid = None
        self._cid = 0

    def _rpc(self, method, params):
        self._cid += 1
        body = {"jsonrpc": "2.0", "id": self._cid,
                "method": method, "params": params}
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(
            self.base_url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(
                    req, timeout=THRESHER_RPC_CUTOFF_S) as r:
                if not self.sid:
                    self.sid = r.headers.get("Mcp-Session-Id")
                raw = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 -- transport failure is data
            raise McpError("thresher rpc failed: %s" % e)
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line.startswith("{"):
                return json.loads(line)
        raise McpError("thresher rpc: no JSON in response")

    def session(self):
        if self.sid:
            return self.sid
        self._rpc("initialize",
                  {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "oracle-market-mcp-apply",
                                  "version": "1.0"}})
        if not self.sid:
            raise McpError("thresher returned no session id")
        return self.sid

    def _intent(self, op):
        return {"operation_type": op, "data_sensitivity": "internal",
                "reason": "oracle-market mcp apply (approved task)"}

    def call_read(self, name, args):
        self.session()
        return _unwrap(self._rpc(
            "tools/call",
            {"name": "call_tool_read",
             "arguments": {"name": name, "args_json": json.dumps(args),
                           "intent": self._intent("read")}}))

    def call_destructive(self, name, args):
        self.session()
        return _unwrap(self._rpc(
            "tools/call",
            {"name": "call_tool_destructive",
             "arguments": {"name": name, "args_json": json.dumps(args),
                           "intent": self._intent("write")}}))


def _check_path(path):
    """Sandbox guard: absolute path under ALLOWED_ROOTS, no .. escapes."""
    if not path or not isinstance(path, str):
        raise McpError("edit rejected: empty path")
    p = Path(path)
    if not p.is_absolute():
        raise McpError("edit rejected (not absolute): %s" % path)
    norm = os.path.normpath(path)
    if not any(norm == r.rstrip("/") or norm.startswith(r.rstrip("/") + "/")
               for r in ALLOWED_ROOTS):
        raise McpError("edit rejected (outside allowed roots): %s" % path)
    return norm


def _local_apply(change_set, evidence):
    """Visible fallback: same anchoring rules, local file IO."""
    applied, failures = 0, []
    for i, edit in enumerate(change_set[:MAX_EDITS_PER_TASK]):
        rec = {"edit": i, "path": edit.get("path"), "via": "local-fallback"}
        try:
            path = _check_path(edit.get("path"))
            old, new = edit.get("old"), edit.get("new")
            if not old:
                rec.update(ok=False, error="empty anchor")
                failures.append(rec); evidence.append(rec); continue
            text = Path(path).read_text(encoding="utf-8")
            n = text.count(old)
            rec["anchor_hits"] = n
            if n != 1:
                rec.update(ok=False,
                           error="anchor_not_unique" if n > 1 else "anchor_missing")
                failures.append(rec); evidence.append(rec); continue
            Path(path).write_text(text.replace(old, new, 1), encoding="utf-8")
            verify = Path(path).read_text(encoding="utf-8")
            if new not in verify:
                rec.update(ok=False, error="verify_failed")
                failures.append(rec); evidence.append(rec); continue
            rec["ok"] = True; applied += 1
        except (OSError, McpError) as e:  # noqa: BLE001
            rec.update(ok=False, error=str(e)[:160])
            failures.append(rec)
        evidence.append(rec)
    return applied, failures


def apply_change_set(change_set, evidence):
    """Apply anchored edits via Thresher MCP tools.

    change_set: [{"path": abs repo path, "old": exact anchor text,
                  "new": replacement text}, ...].
    evidence: list this function appends one record per edit and per MCP
              call to (tool-call evidence for the task record).
    Returns (n_applied, failures). On any Thresher failure the whole set
    falls back to local apply -- recorded visibly in evidence, never
    silent.
    """
    if not change_set:
        evidence.append({"mcp_apply": "empty change set, nothing to apply"})
        return 0, []
    try:
        gh = ThresherMCP()
        gh.session()
    except McpError as e:  # noqa: BLE001
        evidence.append({"mcp": "unavailable", "error": str(e)[:200],
                         "fallback": "local-apply"})
        return _local_apply(change_set, evidence)
    applied, failures = 0, []
    for i, edit in enumerate(change_set[:MAX_EDITS_PER_TASK]):
        rec = {"edit": i, "path": edit.get("path"), "via": "mcp"}
        try:
            path = _check_path(edit.get("path"))
            old, new = edit.get("old"), edit.get("new")
            if not old:
                rec.update(ok=False, error="empty anchor")
                failures.append(rec); evidence.append(rec); continue
            text = gh.call_read(READ_TOOL, {"path": path})
            rec["mcp_calls"] = ["read_text_file"]
            n = text.count(old)
            rec["anchor_hits"] = n
            if n != 1:
                rec.update(ok=False,
                           error="anchor_not_unique" if n > 1 else "anchor_missing")
                failures.append(rec); evidence.append(rec); continue
            gh.call_destructive(EDIT_TOOL, {"path": path, "edits": [
                {"oldText": old, "newText": new}]})
            rec["mcp_calls"].append("edit_file")
            verify = gh.call_read(READ_TOOL, {"path": path})
            rec["mcp_calls"].append("read_text_file:verify")
            if new not in verify:
                rec.update(ok=False, error="verify_failed")
                failures.append(rec); evidence.append(rec); continue
            rec["ok"] = True; applied += 1
        except McpError as e:  # noqa: BLE001
            rec.update(ok=False, error="mcp_error: %s" % str(e)[:160])
            failures.append(rec)
        evidence.append(rec)
    return applied, failures


def parse_edits_json(text):
    """Parse a model-emitted change set. Accepts {"edits": [...]} or a
    bare [...] list. Returns (edits, error)."""
    if not (text or "").strip():
        return [], "empty model output"
    # Whichever bracket opens first wins: a bare [...] list must not
    # lose to the dict hiding inside it.
    pairs = [("{", "}"), ("[", "]")]
    try:
        firsts = sorted(((text.index(o), o, c) for o, c in pairs))
    except ValueError:
        return [], "no JSON object/array in model output"
    obj = None
    for _, open_c, close_c in firsts:
        try:
            start = text.index(open_c)
            end = text.rindex(close_c) + 1
            obj = json.loads(text[start:end])
            break
        except ValueError:
            continue
    if obj is None:
        return [], "no JSON object/array in model output"
    edits = obj.get("edits") if isinstance(obj, dict) else obj
    if not isinstance(edits, list):
        return [], "JSON has no edits list"
    clean = []
    for e in edits:
        if isinstance(e, dict) and e.get("path") and e.get("old") is not None \
                and e.get("new") is not None:
            clean.append({"path": e["path"], "old": e["old"], "new": e["new"]})
    return clean, ""
