#!/usr/bin/env python3
"""Sequence allocator CLI shim for squawk.

Delegates to chat_core._next_seq (mkdir lock + durable .seqhigh mark).
This script exists solely because the hatch cell's ~/workspace/bin/squawk
shells out to it via yote-conn for fleet sends. All allocation logic lives
in chat_core -- this is a thin wrapper, not a second implementation.

Replaces the old standalone seq_alloc.py (2026-09-21, flock-based, deleted
in 4323dda during the squawk migration). The old had its own lock mechanism
(flock) separate from the mkdir lock the new code uses; this shim uses the
single mkdir lock via chat_core.

Usage:
    seq_alloc.py <root> <channel>                -> print allocated seq
    seq_alloc.py --seed <root> <channel> <floor> -> ensure mark >= floor
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_core import (
    _acquire_lock,
    _next_seq,
    _release_lock,
    _seed_seqhigh,
)


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[1] == "--seed":
        root = Path(argv[2])
        channel = argv[3]
        floor = int(argv[4])
        chan = root / channel
        chan.mkdir(parents=True, exist_ok=True)
        lock = _acquire_lock(chan)
        try:
            print(_seed_seqhigh(chan, floor))
        finally:
            _release_lock(lock)
        return 0
    if len(argv) == 3:
        root = Path(argv[1])
        channel = argv[2]
        chan = root / channel
        chan.mkdir(parents=True, exist_ok=True)
        lock = _acquire_lock(chan)
        try:
            print(_next_seq(chan))
        finally:
            _release_lock(lock)
        return 0
    sys.stderr.write(
        "usage: seq_alloc.py <root> <channel>\n"
        "       seq_alloc.py --seed <root> <channel> <floor>\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
