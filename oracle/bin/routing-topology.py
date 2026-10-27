#!/usr/bin/env python3
"""routing-topology — expose the LIVE router alias map to the oracle.

The oracle used to read `herd.yaml` (a YAML file in the estate config
store) to learn which upstream provider each alias forwards to, so it can
attribute a judge failure to the PROVIDER rather than the alias. That file
is gone: the routing SSOT is now
`pens/geode/products/rhodochrosite/routers/strategies/router_config.ts`
(a TypeScript module exporting `CODING: Record<string, [provider, model]>`).

This adapter parses that module and emits the oracle's expected shape:
    {alias: [target, standby, ...]}
where `target` is the provider-qualified model id.

Usage:
  routing-topology.py                 # JSON on stdout
  routing-topology.py --alias openai/gpt-oss-120b
"""
import json
import os
import re
import sys

DEFAULT_TS = (
    "/home/toxic/pens/geode/products/rhodochrosite/routers/strategies/router_config.ts"
)
DEFAULT_STORE = "/home/toxic/.hodos-data/config.json"

# `alias: ["provider", "model"],` inside the CODING record.
_ENTRY_RE = re.compile(
    r"""^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_][\w.\-]*))\s*:\s*"""
    r"""\[\s*"([^"]+)"\s*,\s*([^,\]]+?)\s*\]""",
    re.M,
)
# `alias: null,` — a retired alias.
_NULL_RE = re.compile(
    r"""^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_][\w.\-]*))\s*:\s*null\s*,""",
    re.M,
)


def _unquote(tok: str) -> str:
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    return tok


def parse(path: str) -> dict:
    """{alias: [provider/model, ...]} from the live router config."""
    if not os.path.exists(path):
        return parse_store(DEFAULT_STORE)
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    # Only the CODING record holds the alias -> [provider, model] pairs.
    start = text.find("export const CODING")
    if start < 0:
        start = 0
    end = text.find("\nexport const ", start + 10)
    if end < 0:
        end = len(text)
    block = text[start:end]

    out = {}
    for m in _ENTRY_RE.finditer(block):
        alias = m.group(1) or m.group(2) or m.group(3)
        provider = m.group(4)
        model = _unquote(m.group(5))
        if not alias or not provider:
            continue
        out[alias] = ["%s/%s" % (provider, model)]
    for m in _NULL_RE.finditer(block):
        alias = m.group(1) or m.group(2) or m.group(3)
        if alias:
            out.setdefault(alias, [])
    # The estate routing lanes (estate/auto, estate/code, ...) live in the
    # RUNTIME store, not the static TS config — merge them in so provider
    # attribution resolves for the lanes the oracle actually judges with.
    for alias, targets in parse_store(DEFAULT_STORE).items():
        out.setdefault(alias, targets)
    return out


def parse_store(path: str) -> dict:
    """{alias: [provider/model, ...]} from the router's runtime config store.

    The store (DATA_DIR/config.json) holds each provider's `model_map`:
    {"estate/auto": "qwen3.6-35b", ...}. The provider that serves a lane
    is the one whose `models` list contains the mapped model.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    out = {}
    for p in data.get("providers") or []:
        pname = p.get("name") or ""
        models = p.get("models") or []
        for alias, model in (p.get("model_map") or {}).items():
            if not isinstance(model, str):
                continue
            out.setdefault(alias, [])
            if model in models:
                out[alias].append("%s/%s" % (pname, model))
    return out


def main() -> int:
    path = os.environ.get("ROUTER_CONFIG_TS", DEFAULT_TS)
    argv = sys.argv[1:]
    if argv and argv[0] == "--alias" and len(argv) > 1:
        topo = parse(path)
        want = argv[1]
        print(json.dumps(topo.get(want, [])))
        return 0
    if argv and argv[0] == "--path":
        print(path)
        return 0
    print(json.dumps(parse(path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
