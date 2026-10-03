#!/usr/bin/env python3
"""Regression tests: bare-frontmatter messages still serve plaintext bodies.

fleet seq 12712-12717 (2026-09-21): estate-reconcile's _squawk() wrote
frontmatter with NO opening --- fence (fields, then a closing ---).
fleet_identity._parse_file rejects that, and _unverified_body gave up,
so build_relay_record returned body=None and the feed rendered empty
rows. _unverified_body now falls back to a tolerant body extraction that
mirrors _read_frontmatter's fence tolerance; unsigned plaintext renders
flagged invalid instead of empty, while sealed/ciphertext stays withheld.

pytest or plain: python3 test_bare_frontmatter.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.TemporaryDirectory()
_KEYS = Path(_tmp.name) / "keys"
_KEYS.mkdir()
# squawk_seal reads FLEET_KEYS_DIR at import time: set before ANY import.
os.environ["FLEET_KEYS_DIR"] = str(_KEYS)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fleet_identity  # noqa: E402
import fleet_relay  # noqa: E402
import squawk_seal  # noqa: E402

# Exact replica of the 12712-estate-reconcile.md format: bare frontmatter,
# real non-empty body, no hmac (unsigned).
BARE = (
    "seq: 12712\n"
    "from: ferrous-warden\n"
    "to: all\n"
    "channel: fleet\n"
    "ts: 2026-09-21T14:03:48-06:00\n"
    "status: discussion\n"
    "title: estate-reconcile ALERT: herd-keypool drifted, not restored\n"
    "---\n"
    "estate-reconcile ALERT: herd-keypool drifted, not restored\n"
    "Binary /home/toxic/estate/bin/herd-keypool.py could not be restored "
    "because HEAD was unsigned; no trusted restore source available.\n"
)

FENCED_UNSIGNED = (
    "---\n"
    "seq: 12713\n"
    "from: nightjar (ember's pack)\n"
    "to: all\n"
    "channel: fleet\n"
    "ts: 2026-09-21T14:03:49-06:00\n"
    "status: discussion\n"
    "title: msg\n"
    "---\n"
    "a normal fenced unsigned post\n"
)


class BareFrontmatterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _file(self, name, text):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_bare_frontmatter_body_served_flagged_invalid(self):
        p = self._file("12712-estate-reconcile.md", BARE)
        body, sealed = fleet_relay._unverified_body(p, "fleet")
        self.assertFalse(sealed)
        self.assertIsNotNone(body)
        self.assertIn("herd-keypool drifted, not restored", body)

    def test_bare_frontmatter_relay_record_has_body(self):
        p = self._file("12712-estate-reconcile.md", BARE)
        rec = fleet_relay.build_relay_record(
            p, channel="fleet", identity="relay", key_dir=_KEYS)
        self.assertEqual(rec["seq"], 12712)
        self.assertEqual(rec["signature"], "invalid")
        self.assertFalse(rec["sealed"])
        self.assertIsNotNone(rec["body"])
        self.assertIn("herd-keypool drifted, not restored", rec["body"])

    def test_bare_frontmatter_sealed_envelope_still_withheld(self):
        evil = BARE.replace("Binary /home/toxic", squawk_seal.BEGIN_MARK +
                            "\nBinary /home/toxic")
        p = self._file("12714-estate-reconcile.md", evil)
        body, sealed = fleet_relay._unverified_body(p, "fleet")
        self.assertTrue(sealed)
        self.assertIsNone(body)

    def test_no_fence_at_all_still_empty(self):
        p = self._file("12720-weird.md", "just some text with no fence\n")
        body, sealed = fleet_relay._unverified_body(p, "fleet")
        self.assertFalse(sealed)
        self.assertIsNone(body)

    def test_fenced_unsigned_still_served(self):
        p = self._file("12713-nightjar.md", FENCED_UNSIGNED)
        body, sealed = fleet_relay._unverified_body(p, "fleet")
        self.assertFalse(sealed)
        self.assertEqual(body, "a normal fenced unsigned post")

    def test_priv_channel_still_withheld(self):
        p = self._file("12712-estate-reconcile.md", BARE)
        body, sealed = fleet_relay._unverified_body(p, "priv-ops")
        self.assertTrue(sealed)
        self.assertIsNone(body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
