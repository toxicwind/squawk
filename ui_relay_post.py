#!/usr/bin/env python3
"""Thin signed human post for squawk-ui /send.

Same writer as chat.py relay-in (chat_commands._post_message) without
CLI argparse overhead. Pattern-forge race 2026-10-07: ~63ms vs ~73ms CLI;
first-valid-wins → this is the hot path. Usage:
  python3 ui_relay_post.py --root ROOT --channel CHAN --from HUMAN --text TEXT [--title T]
Prints: relayed #<seq> -> <channel>/<fname> (human: <human>)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# squawk/ is the cwd / sibling of this file
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chat_commands  # noqa: E402
import fleet_relay  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--channel", required=True)
    ap.add_argument("--from", dest="human", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--title", default="msg")
    a = ap.parse_args()
    root = Path(a.root)
    kd = root / "keys"
    fleet_relay.ensure_keys_env(root=root)
    identity = fleet_relay.resolve_identity(None)
    body = fleet_relay.seal_for_channel(a.channel, a.text)
    seq, fname = chat_commands._post_message(
        root,
        a.channel,
        body=body,
        sender=identity,
        to="all",
        status="discussion",
        title=a.title,
        extra_frontmatter={
            "relayed_from": fleet_relay.RELAYED_FROM,
            "human": a.human,
        },
        key_dir=kd if kd.is_dir() else None,
    )
    print(f"relayed #{seq} -> {a.channel}/{fname} (human: {a.human})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
