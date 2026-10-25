#!/usr/bin/env python3
"""hindsight_mcp_server.py — MCP server exposing Hindsight's shared `estate` bank.

Lets Kappa (and any MCP client) recall/retain/reflect against the SAME Hindsight
bank that Tau uses (`bank_id = "estate"`), giving both harnesses one coherent
long-term memory plane.

Backend: Vectorize Hindsight at HINDSIGHT_API_URL (default http://127.0.0.1:25117).
Bank:    HINDSIGHT_BANK (default "estate").
Contract (from estate/docs/tools/{recall,retain,reflect}.md and live probes):
  ensure bank : PUT  /v1/default/banks/{bank}            (docker image needs no body here)
  recall      : POST /v1/default/banks/{bank}/memories/recall
  retain      : POST /v1/default/banks/{bank}/memories
  reflect     : POST /v1/default/banks/{bank}/reflect
Transport: stdio JSON-RPC (MCP). Zero third-party deps (stdlib http.client + json),
matching the rest of squawk. Run via `python3 hindsight_mcp_server.py`.

Endpoints exposed (tools):
  hindsight_recall(query, budget="mid", max_tokens=1024, types=null, tags=null)
  hindsight_retain(content, context=null, tags=null)
  hindsight_reflect(query=null, budget="low")
  hindsight_list_banks()
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

API_URL = os.environ.get("HINDSIGHT_API_URL", "http://127.0.0.1:25117").rstrip("/")
BANK = os.environ.get("HINDSIGHT_BANK", "estate")


def _req(method: str, path: str, body: dict | None = None, timeout: float = 30.0):
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = str(e)
        return e.code, {"error": detail}


def _ensure_bank() -> None:
    """Best-effort create the estate bank. Hindsight's agent client auto-creates on
    first retain anyway; swallowing here matches that behavior."""
    status, _ = _req("PUT", f"/v1/default/banks/{BANK}")
    # 200/201 = created; 404/422 on a bare PUT are tolerated (client creates it later)
    if status in (200, 201, 404, 422):
        return
    # Other statuses logged, not fatal.


def _recall(query="", budget="mid", max_tokens=1024, types=None, tags=None):
    body = {"query": query, "budget": budget, "max_tokens": max_tokens}
    if types:
        body["types"] = types
    if tags:
        body["tags"] = tags
    status, data = _req("POST", f"/v1/default/banks/{BANK}/memories/recall", body)
    if status != 200:
        return {"ok": False, "status": status, "error": data}
    results = data.get("results", data.get("memories", data))
    return {"ok": True, "results": results}


def _retain(content, context=None, tags=None):
    _ensure_bank()
    item = {"content": content}
    if context:
        item["context"] = context
    if tags:
        item["tags"] = tags
    # The Hindsight backend's /memories endpoint expects {"items": [...]} (matches
    # retainBatch). Sending {"memories": [...]} returns 422 (body.items required).
    # async=true returns immediately with an operation_id; sync retain runs the
    # extraction pipeline and can take >20s (no memory is lost — evented later).
    status, data = _req(
        "POST", f"/v1/default/banks/{BANK}/memories", {"async": True, "items": [item]}
    )
    if status not in (200, 201):
        return {"ok": False, "status": status, "error": data}
    return {"ok": True, **data}


def _reflect(query=None, budget="low"):
    _ensure_bank()
    body = {"budget": budget}
    if query:
        body["query"] = query
    status, data = _req("POST", f"/v1/default/banks/{BANK}/reflect", body)
    if status != 200:
        return {"ok": False, "status": status, "error": data}
    return {"ok": True, **data}


def _list_banks():
    status, data = _req("GET", "/v1/default/banks")
    if status != 200:
        return {"ok": False, "status": status, "error": data}
    return {"ok": True, "banks": data.get("banks", [])}


TOOLS = {
    "hindsight_recall": {
        "name": "hindsight_recall",
        "description": f"Recall memories from the shared Hindsight '{BANK}' bank (same bank Tau uses).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                },
                "budget": {
                    "type": "string",
                    "enum": ["low", "mid", "high"],
                    "default": "mid",
                },
                "max_tokens": {"type": "integer", "default": 1024},
                "types": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
    },
    "hindsight_retain": {
        "name": "hindsight_retain",
        "description": f"Store a durable fact into the shared Hindsight '{BANK}' bank.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Self-contained fact/memory to store",
                },
                "context": {"type": "string", "description": "Optional provenance"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content"],
        },
    },
    "hindsight_reflect": {
        "name": "hindsight_reflect",
        "description": f"Run agentic reflection over the shared Hindsight '{BANK}' bank.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "budget": {
                    "type": "string",
                    "enum": ["low", "mid", "high"],
                    "default": "low",
                },
            },
        },
    },
    "hindsight_list_banks": {
        "name": "hindsight_list_banks",
        "description": "List Hindsight banks (confirm 'estate' exists).",
        "inputSchema": {"type": "object", "properties": {}},
    },
}

HANDLERS = {
    "hindsight_recall": _recall,
    "hindsight_retain": _retain,
    "hindsight_reflect": _reflect,
    "hindsight_list_banks": _list_banks,
}


def _jsonrpc(msg: dict) -> dict:
    m = msg.get("method")
    if m == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "hindsight-mcp", "version": "1.0.0"},
            },
        }
    if m == "notifications/initialized" or m is None:
        return {}
    if m == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "result": {"tools": list(TOOLS.values())},
        }
    if m == "tools/call":
        tool = msg.get("params", {}).get("name")
        args = msg.get("params", {}).get("arguments", {}) or {}
        if tool in HANDLERS:
            res = HANDLERS[tool](**args)
            text = json.dumps(res, ensure_ascii=False)
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {"content": [{"type": "text", "text": text}]},
            }
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32601, "message": f"unknown tool {tool}"},
        }
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "error": {"code": -32601, "message": f"unknown method {m}"},
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        out = _jsonrpc(msg)
        if out:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
