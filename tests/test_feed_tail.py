#!/usr/bin/env python3
"""Tests for squawk-feed tail snapshots, numeric ordering, tolerant
frontmatter, and the ?channel= parameter. pytest or plain unittest."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

_tmp = tempfile.TemporaryDirectory()
_KEYS = Path(_tmp.name) / "keys"
_KEYS.mkdir()
# squawk_seal reads FLEET_KEYS_DIR at import time: set before ANY import.
os.environ["FLEET_KEYS_DIR"] = str(_KEYS)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chat  # noqa: E402
import fleet_identity  # noqa: E402
import fleet_relay  # noqa: E402

for _agent in ("relay", "alice"):
    try:
        fleet_identity.keygen(_agent, kd=_KEYS)
    except Exception:
        pass
import squawk_feed  # noqa: E402

TOKEN = "test-bearer-token"


def _get(port, path, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


class FeedTailTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="feedtail-root-"))
        chat.cmd_init(
            self.root,
            SimpleNamespace(channel="fleet", members="relay,alice",
                            topic="test", ephemeral=None),
        )
        self.state_server = None
        self.srv_thread = None

    def tearDown(self):
        if self.state_server is not None:
            self.state_server.stop_watchers()
            self.state_server.shutdown()
            self.state_server.server_close()
        if self.srv_thread is not None:
            self.srv_thread.join(timeout=10)

    def _serve(self, hold=55.0):
        server = squawk_feed.serve(
            root=self.root, channel="fleet", identity="relay",
            key_dir=_KEYS, bind="127.0.0.1", port=0, token=TOKEN, hold=hold)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        self.state_server = server
        self.srv_thread = t
        return server.server_address[1]

    def _post(self, body, sender="relay"):
        return chat._post_message(
            self.root, "fleet", body=body, sender=sender,
            title="test", key_dir=_KEYS)

    # -- numeric ordering -------------------------------------------------
    def test_new_messages_numeric_order(self):
        d = Path(_tmp.name) / "numdir"
        d.mkdir(exist_ok=True)
        for n in ("9-a.md", "10-b.md", "100-c.md", "1000-d.md"):
            (d / n).write_text("---\nseq: 1\n---\nx\n")
        got = [p.name for p in squawk_feed._new_messages(d, 0)]
        self.assertEqual(got, ["9-a.md", "10-b.md", "100-c.md", "1000-d.md"])

    # -- tail snapshots ----------------------------------------------------
    def test_tail_returns_recent_in_one_shot(self):
        for i in range(120):
            self._post(f"msg-{i}")
        port = self._serve()
        status, obj = _get(port, "/squawk-feed/wait?since=0&tail=200",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(len(obj["messages"]), 120)
        seqs = [m["seq"] for m in obj["messages"]]
        self.assertEqual(seqs, sorted(seqs))  # oldest first
        # cursor lands on the live high-water mark: no drain needed
        _, ping = _get(port, "/squawk-feed/ping")
        self.assertEqual(obj["seq"], ping["seq"])

    def test_tail_bounded(self):
        for i in range(120):
            self._post(f"msg-{i}")
        port = self._serve()
        _, ping = _get(port, "/squawk-feed/ping")
        high = ping["seq"]
        status, obj = _get(port, "/squawk-feed/wait?since=0&tail=50",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(len(obj["messages"]), 50)
        seqs = [m["seq"] for m in obj["messages"]]
        self.assertEqual(seqs[0], high - 49)
        self.assertEqual(seqs[-1], high)
        self.assertEqual(obj["seq"], high)

    def test_tail_capped_server_side(self):
        self._post("one")
        port = self._serve()
        status, obj = _get(port, "/squawk-feed/wait?since=0&tail=5000",
                           token=TOKEN)
        self.assertEqual(status, 200)
        # capped at TAIL_CAP; must not blow up or hang
        self.assertLessEqual(len(obj["messages"]), squawk_feed.TAIL_CAP)

    def test_tail_never_parks(self):
        port = self._serve()
        t0 = time.monotonic()
        status, _ = _get(port, "/squawk-feed/wait?since=999999999&tail=10",
                         token=TOKEN)
        dt = time.monotonic() - t0
        self.assertEqual(status, 200)
        self.assertLess(dt, 5.0)  # immediate; classic path would hold 55s

    # -- drain progress guarantee ------------------------------------------
    def test_drain_advances_past_seq0_records(self):
        seq, _ = self._post("real")
        # a malformed file: matches the name pattern, unparseable body
        bad = self.root / "fleet" / f"{seq + 1}-broken.md"
        bad.write_text("this is not frontmatter at all\n")
        port = self._serve(hold=2.0)
        status, obj = _get(port, f"/squawk-feed/wait?since={seq}",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(len(obj["messages"]), 1)
        # cursor advanced past the broken file: no infinite refetch
        self.assertGreater(obj["seq"], seq)
        status2, obj2 = _get(port, f"/squawk-feed/wait?since={obj['seq']}",
                             token=TOKEN)
        self.assertEqual(obj2["messages"], [])

    # -- tolerant frontmatter -----------------------------------------------
    def test_frontmatter_without_opening_fence(self):
        p = Path(_tmp.name) / "nofm.md"
        p.write_text("seq: 42\nfrom: alice\nchannel: fleet\n---\nhello\n")
        meta = fleet_relay._read_frontmatter(p)
        self.assertEqual(meta["seq"], "42")
        self.assertEqual(meta["from"], "alice")

    def test_frontmatter_classic_still_works(self):
        p = Path(_tmp.name) / "fm.md"
        p.write_text("---\nseq: 7\nfrom: relay\n---\nbody\n")
        meta = fleet_relay._read_frontmatter(p)
        self.assertEqual(meta["seq"], "7")

    # -- ?channel= ------------------------------------------------------------
    def test_channel_param(self):
        port = self._serve()
        status, obj = _get(port, "/squawk-feed/wait?since=0&channel=fleet",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertIn("messages", obj)
        # unknown channel -> 404 (never reveal)
        status, _ = _get(port, "/squawk-feed/wait?since=0&channel=nope",
                         token=TOKEN)
        self.assertEqual(status, 404)
        # traversal / garbage -> 404
        for bad in ("../x", "..", "a/b", ".hidden"):
            status, _ = _get(
                port, f"/squawk-feed/wait?since=0&channel={bad}",
                token=TOKEN)
            self.assertEqual(status, 404, bad)
        # empty channel param falls back to the default channel
        status, obj = _get(port, "/squawk-feed/wait?since=0&channel=",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertIn("messages", obj)


if __name__ == "__main__":
    unittest.main(verbosity=2)
