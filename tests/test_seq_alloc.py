#!/usr/bin/env python3
"""Tests for the maximal sequence allocator (chat_core._next_seq + seq_alloc shim).

Covers the 2026-09-21 regression (seq reuse after file deletion) and the
new durable-mark fast path.

Run: python3 -m pytest tests/test_seq_alloc.py -q   (or plain python3)
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_core import (
    _acquire_lock,
    _next_seq,
    _read_seqhigh,
    _release_lock,
    _seed_seqhigh,
    max_seq,
)


def _msg(chan: Path, seq: int, sender: str = "tester") -> Path:
    p = chan / f"{seq:04d}-{sender}-msg.md"
    p.write_text("---\nseq: %d\nfrom: %s\n---\nhello\n" % (seq, sender))
    return p


def _alloc(chan: Path) -> int:
    """Allocate under lock, like chat_commands.post does."""
    lock = _acquire_lock(chan)
    try:
        return _next_seq(chan)
    finally:
        _release_lock(lock)


class TestNextSeq(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.chan = self.root / "fleet"
        self.chan.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_channel_starts_above_disk(self):
        # Slow path: no mark yet, scan disk to start above pre-existing files.
        for s in (3, 7, 12):
            _msg(self.chan, s)
        self.assertEqual(_alloc(self.chan), 13)
        # Mark now exists; fast path takes over.
        self.assertEqual(_read_seqhigh(self.chan), 13)
        self.assertEqual(_alloc(self.chan), 14)

    def test_monotonic_across_deletion(self):
        # The 2026-09-21 regression: files deleted, allocator must NOT
        # reuse the dead numbers.
        for s in range(1, 7):
            _msg(self.chan, s)
        self.assertEqual(_alloc(self.chan), 7)
        # Delete the top files (simulating the 12811-12816 loss).
        for s in (5, 6, 7):
            p = self.chan / f"{s:04d}-tester-msg.md"
            if p.exists():
                p.unlink()
        # Disk max is now 4; allocator must still go above 7.
        self.assertEqual(_alloc(self.chan), 8)
        self.assertEqual(_alloc(self.chan), 9)
        # Verify the mark persisted.
        self.assertEqual(_read_seqhigh(self.chan), 9)

    def test_wiped_mark_falls_back_to_disk(self):
        for s in (1, 2, 3):
            _msg(self.chan, s)
        self.assertEqual(_alloc(self.chan), 4)
        (self.chan / ".seqhigh").unlink()
        # Operator wiped the mark: safe fallback is disk+1 (slow path),
        # never below what is on disk.
        self.assertEqual(_alloc(self.chan), 4)
        self.assertEqual(_alloc(self.chan), 5)

    def test_empty_channel_starts_at_one(self):
        self.assertEqual(_alloc(self.chan), 1)
        self.assertEqual(_alloc(self.chan), 2)

    def test_seed_ensures_floor(self):
        for s in (1, 2, 3):
            _msg(self.chan, s)
        lock = _acquire_lock(self.chan)
        try:
            # Seed below disk max: mark goes to disk max.
            self.assertEqual(_seed_seqhigh(self.chan, 2), 3)
            # Seed above: mark goes to floor.
            self.assertEqual(_seed_seqhigh(self.chan, 100), 100)
        finally:
            _release_lock(lock)
        # Next alloc continues above the seed.
        self.assertEqual(_alloc(self.chan), 101)

    def test_fast_path_no_disk_scan(self):
        # After the mark exists, _next_seq should NOT need max_seq.
        # We verify by checking the mark file is the source of truth.
        self.assertEqual(_alloc(self.chan), 1)
        # Manually verify: mark file contains 1.
        mark_content = (self.chan / ".seqhigh").read_text().strip()
        self.assertEqual(mark_content, "1")
        # Allocate 10 more; each should be mark+1 without scanning.
        for expected in range(2, 12):
            self.assertEqual(_alloc(self.chan), expected)
        self.assertEqual(_read_seqhigh(self.chan), 11)

    def test_concurrent_allocations_unique(self):
        # Simulate concurrent allocators (threads, same process).
        # The mkdir lock serializes them.
        import threading
        results = []
        errors = []
        def worker():
            try:
                for _ in range(10):
                    results.append(_alloc(self.chan))
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 50)
        self.assertEqual(len(set(results)), 50)  # all unique
        self.assertEqual(sorted(results), list(range(1, 51)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
