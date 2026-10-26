#!/usr/bin/env python3
"""refresh_rejoin_cursor.py - one-shot stateless refresh/rejoin packet reader.

Refresh is the SAME one-shot join-packet read at a newer cursor:
  refresh(source, cursor) -> packet

  Given cursor N (line offset into an append-only chat source, newest lines
  at the bottom), return everything after N: the last five message lines
  after N plus the LATEST decision verbatim, and a NEW cursor M (= total
  line count). A stale/invalid cursor is clamped fail-open (negative -> 0,
  beyond-end -> total), never an error.

Decision semantics: the decision field resolves last-writer-wins -- it is
always the newest "DECISION:" line in the whole source, regardless of the
cursor. Two decisions after the cursor -> the newer one wins.

Idempotency: the operation is a pure read (no writes, no state, no daemon
contact). refresh(source, M) twice returns byte-identical packets with no
side effects and no duplicates: messages_after_cursor is empty on the
second call because M already covers the tail.

Line protocol of the source file (append-only, newest-at-bottom):
  - decision line: starts with "DECISION:" -> value is the line verbatim
  - any other non-empty line: a message line
Blank lines are ignored for messages but still count toward the cursor.

Usage:
  python3 refresh_rejoin_cursor.py <source_file> <cursor>
Prints one JSON packet to stdout. Exit 0 always (fail-open).
"""

import json
import sys

DECISION_PREFIX = "DECISION:"
MAX_MESSAGES = 5


def read_source(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        # Fail-open: unreadable source -> empty source, cursor 0.
        return []


def is_decision(line):
    return line.startswith(DECISION_PREFIX)


def refresh(path, cursor):
    lines = read_source(path)
    total = len(lines)
    try:
        n = int(cursor)
    except (TypeError, ValueError):
        n = 0
    # Fail-open clamping: stale, negative, or future cursors never error.
    n = max(0, min(n, total))

    new_lines = lines[n:]
    messages = [l for l in new_lines if l.strip() and not is_decision(l)]
    messages = messages[-MAX_MESSAGES:]

    # Last-writer-wins: newest DECISION: line in the whole source.
    decision = None
    decision_index = None
    for i, l in enumerate(lines):
        if is_decision(l):
            decision = l
            decision_index = i + 1  # 1-based line number

    return {
        "source": path,
        "cursor_in": n,
        "cursor_out": total,
        "messages_after_cursor": len(new_lines),
        "messages": messages,
        "decision": decision,               # verbatim, newest wins
        "decision_line": decision_index,    # 1-based, None if no decision
        "side_effects": False,              # pure read; idempotent by construction
    }


def main(argv):
    if len(argv) != 3:
        print(json.dumps({
            "error": "usage: refresh_rejoin_cursor.py <source_file> <cursor>",
            "side_effects": False,
        }))
        return 0
    path, cursor = argv[1], argv[2]
    print(json.dumps(refresh(path, cursor), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
