#!/usr/bin/env python3
"""Tests for squawk-feed (bearer-authed fat long-poll). pytest or plain.

Covers: /ping public + content-free; /wait + /subscribe alias both 404
without/invalid bearer and 200 with it; fat response shape (per-message
seq, 50-cap cursor protocol); wake on post; timeout; 500-char truncation;
sealed envelopes unsealed server-side (fail closed when unopenable).
"""

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

for _agent in ("alice", "bob", "mallory", "recovery", "system"):
    try:
        fleet_identity.keygen(_agent, kd=_KEYS)
    except Exception:
        pass
import squawk_feed  # noqa: E402

TOKEN = "test-bearer-token-xyz"

try:
    import squawk_seal
    _nacl_ok = True
    try:
        squawk_seal._nacl()
    except RuntimeError:
        _nacl_ok = False
except ImportError:
    squawk_seal = None
    _nacl_ok = False


def _get(port, path, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


class SquawkFeedFatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(_tmp.name) / "chat-root"
        for _a in ("relay", "alice"):
            try:
                fleet_identity.keygen(_a, kd=_KEYS)
            except Exception:
                pass
        if _nacl_ok:
            squawk_seal.keygen("relay", keys_dir=_KEYS)
        chat.cmd_init(
            cls.root,
            SimpleNamespace(channel="fleet", members="relay,alice",
                            topic="test", ephemeral=None),
        )

    def setUp(self):
        self.state_server = None
        self.srv_thread = None

    def tearDown(self):
        if self.state_server is not None:
            self.state_server.feed_state.stop.set()
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

    def _high(self, port):
        status, obj = _get(port, "/squawk-feed/ping")
        self.assertEqual(status, 200)
        return obj["seq"]

    # -- /ping: public, content-free ----------------------------------------

    def test_ping_public_content_free(self):
        port = self._serve()
        status, obj = _get(port, "/squawk-feed/ping")  # no auth header
        self.assertEqual(status, 200)
        self.assertEqual(set(obj.keys()), {"seq"})
        before = obj["seq"]
        seq, _fname = self._post("hello")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self._high(port) >= seq:
                break
            time.sleep(0.05)
        self.assertGreaterEqual(self._high(port), seq)
        self.assertGreaterEqual(self._high(port), before)

    # -- auth: 404 without / with wrong bearer -------------------------------

    def test_wait_and_subscribe_require_bearer(self):
        port = self._serve()
        for path in ("/squawk-feed/wait?since=0",
                     "/squawk-feed/subscribe?since=0"):
            status, _obj = _get(port, path)
            self.assertEqual(status, 404, path)
            status, _obj = _get(port, path, token="wrong-token")
            self.assertEqual(status, 404, path)
            status, obj = _get(port, path, token=TOKEN)
            self.assertEqual(status, 200, path)
            self.assertIn("seq", obj)
            self.assertIn("messages", obj)

    def test_unknown_path_404(self):
        port = self._serve()
        status, _obj = _get(port, "/nope", token=TOKEN)
        self.assertEqual(status, 404)

    # -- fat response shape ---------------------------------------------------

    def test_fat_response_per_message_seq(self):
        port = self._serve()
        base = self._high(port)
        self._post("one")
        self._post("two", sender="alice")
        self._post("three")
        status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(obj["seq"], base + 3)
        self.assertEqual(len(obj["messages"]), 3)
        seqs = [m["seq"] for m in obj["messages"]]
        self.assertEqual(seqs, [base + 1, base + 2, base + 3])
        self.assertEqual(obj["messages"][0]["body"], "one")
        self.assertEqual(obj["messages"][1]["from"], "alice")
        self.assertTrue(
            all(m["signature"] == "valid" for m in obj["messages"]))

    def test_text_not_truncated_full_body(self):
        # Design (Chris, 2026-09-21): full bodies -- the 500-char cap
        # was removed; its brief resurrection was migration loss.
        port = self._serve()
        base = self._high(port)
        self._post("y" * 600)
        _status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                            token=TOKEN)
        text = obj["messages"][-1]["body"]
        self.assertEqual(len(text), 600)

    def test_fat_serves_full_body_design(self):
        # DESIGN (Sept 21-28 records; Oct 19 lane brief): the 500-char
        # server-side cap was REMOVED -- long bodies must render in FULL.
        # build_fat still applies _truncate (TEXT_CAP=500); the removal was
        # lost in the estate migration (untraceable in this path's history --
        # only 11 commits follow squawk_feed.py here). This test asserts the
        # DESIGN and is expected to fail until the cap is removed or the
        # design record is revised. Do NOT "fix" it by asserting truncation
        # (that behavior is already codified by test_text_truncated_at_500).
        port = self._serve()
        base = self._high(port)
        self._post("q" * 600)
        _status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                            token=TOKEN)
        self.assertEqual(len(obj["messages"][-1]["body"]), 600)


    # -- wake + timeout --------------------------------------------------------
    def test_wait_tail_returns_most_recent(self):
        # the UI boot path: wait?since=0&tail=N must return the LAST N
        # messages (landing at the live cursor), not the first N.
        port = self._serve()
        base = self._high(port)
        for i in range(6):
            self._post(f"msg{i}")
        status, obj = _get(port, "/squawk-feed/wait?since=0&tail=2",
                           token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(len(obj["messages"]), 2)
        self.assertEqual([m["body"] for m in obj["messages"]],
                         ["msg4", "msg5"])
        self.assertEqual(obj["seq"], base + 6)


    def test_wait_wakes_on_post(self):
        port = self._serve()
        base = self._high(port)
        result = {}

        def waiter():
            _status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                                token=TOKEN)
            result.update(obj)

        t = threading.Thread(target=waiter, daemon=True)
        t.start()
        time.sleep(0.5)  # let the long-poll park
        seq, _fname = self._post("wake me")
        t.join(timeout=15)
        self.assertFalse(t.is_alive(), "long-poll did not wake on post")
        self.assertEqual(result["seq"], seq)
        self.assertEqual(len(result["messages"]), 1)
        self.assertEqual(result["messages"][0]["body"], "wake me")

    def test_wait_timeout_returns_current_empty(self):
        port = self._serve(hold=1.5)
        base = self._high(port)
        start = time.monotonic()
        status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                           token=TOKEN)
        elapsed = time.monotonic() - start
        self.assertEqual(status, 200)
        self.assertEqual(obj, {"seq": base, "messages": []})
        self.assertGreaterEqual(elapsed, 1.0)
        self.assertLess(elapsed, 15.0)

    # -- sealed envelopes -------------------------------------------------------

    def test_sealed_unopenable_fail_closed(self):
        self.assertIsNotNone(squawk_seal, "squawk_seal module required")
        port = self._serve()
        base = self._high(port)
        # envelope for relay, but garbage ciphertext (or no seal key):
        # must NOT be served as content.
        body = squawk_seal.build_envelope("relay", b"\x00" * 64)
        self._post(body)
        _status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                            token=TOKEN)
        rec = obj["messages"][-1]
        self.assertTrue(rec["sealed"])
        self.assertIsNone(rec["body"])
        self.assertEqual(rec["signature"], "valid")

    @unittest.skipUnless(_nacl_ok, "pynacl not available")
    def test_sealed_unsealed_server_side(self):
        port = self._serve()
        base = self._high(port)
        pub = squawk_seal.load_public_key("relay", keys_dir=_KEYS)
        ct = squawk_seal.seal_bytes(pub, b"secret for relay")
        body = squawk_seal.build_envelope("relay", ct)
        self._post(body)
        _status, obj = _get(port, f"/squawk-feed/wait?since={base}",
                            token=TOKEN)
        rec = obj["messages"][-1]
        self.assertTrue(rec["sealed"])
        self.assertEqual(rec["body"], "secret for relay")

class SquawkFeedRendererTests(unittest.TestCase):
    """Renderer-matrix tests over build_relay_record (the feed renderer).

    Clears the fixture debt carried since September: signed / tampered /
    sealed / frontmatter-metadata / long-body / raw-HTML. Record-level
    (no HTTP): the renderer is build_relay_record; the serve path is
    covered by SquawkFeedFatTests.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = Path(_tmp.name) / "render-root"
        if _nacl_ok:
            for _a in ("relay", "bob"):
                try:
                    squawk_seal.keygen(_a, keys_dir=_KEYS)
                except Exception:
                    pass
        chat.cmd_init(
            cls.root,
            SimpleNamespace(channel="fleet", members="relay,alice,bob",
                            topic="renderer", ephemeral=None),
        )

    def _post(self, body, sender="alice", **kw):
        kw.setdefault("title", "test")
        seq, fname = chat._post_message(
            self.root, "fleet", body=body, sender=sender,
            key_dir=_KEYS, **kw)
        return seq, self.root / "fleet" / fname

    def _record(self, path, identity="relay"):
        return fleet_relay.build_relay_record(
            path, channel="fleet", identity=identity, key_dir=_KEYS)

    # -- 1. signed message renders and verifies ----------------------------

    def test_signed_message_valid(self):
        _seq, path = self._post("signed hello", sender="alice")
        rec = self._record(path)
        self.assertEqual(rec["signature"], "valid")
        self.assertFalse(rec["sealed"])
        self.assertIsNone(rec["unseal_error"])
        self.assertEqual(rec["body"], "signed hello")
        self.assertEqual(rec["from"], "alice")
        self.assertEqual(rec["channel"], "fleet")

    # -- 2. tampered message: flagged per code behavior ---------------------

    def test_tampered_message_invalid(self):
        _seq, path = self._post("genuine content", sender="alice")
        raw = path.read_text(encoding="utf-8")
        self.assertIn("genuine content", raw)
        path.write_text(raw.replace("genuine content", "genuine Xcontent"),
                        encoding="utf-8")
        # never raises: signature problems are reported in the record
        rec = self._record(path)
        self.assertEqual(rec["signature"], "invalid")
        # fail-open body, flagged unverified (pre-HMAC history stays readable)
        self.assertEqual(rec["body"], "genuine Xcontent")
        self.assertFalse(rec["sealed"])

    # -- 3. sealed: metadata shown, body withheld ---------------------------

    def test_sealed_unreadable_withholds_body(self):
        self.assertIsNotNone(squawk_seal, "squawk_seal module required")
        body = squawk_seal.build_envelope("relay", b"\x00" * 64)
        _seq, path = self._post(body, sender="relay")
        rec = self._record(path, identity="relay")
        self.assertTrue(rec["sealed"])
        self.assertIsNone(rec["body"])
        # metadata still served: the envelope is attributable, not readable
        self.assertEqual(rec["from"], "relay")
        self.assertEqual(rec["title"], "test")
        self.assertIsNotNone(rec["unseal_error"])

    @unittest.skipUnless(_nacl_ok, "pynacl not available")
    def test_sealed_plaintext_never_leaks(self):
        pub = squawk_seal.load_public_key("bob", keys_dir=_KEYS)
        ct = squawk_seal.seal_bytes(pub, b"top secret for bob only")
        body = squawk_seal.build_envelope("bob", ct)
        _seq, path = self._post(body, sender="relay")
        rec = self._record(path, identity="relay")
        self.assertTrue(rec["sealed"])
        self.assertIsNone(rec["body"])
        self.assertEqual(rec["signature"], "valid")  # file hmac is fine;
        # only the envelope payload is unreadable by relay
        self.assertEqual(rec["from"], "relay")
        blob = json.dumps(rec)
        self.assertNotIn("top secret for bob only", blob)

    # -- 4. frontmatter metadata rendered as the code intends ---------------

    def test_frontmatter_metadata_flows_through(self):
        _seq, path = self._post("memo body", sender="alice", to="bob",
                                title="Quarterly review",
                                status="announcement",
                                extra_frontmatter={"type": "memo"})
        rec = self._record(path)
        self.assertEqual(rec["signature"], "valid")
        self.assertEqual(rec["title"], "Quarterly review")
        self.assertEqual(rec["to"], "bob")
        self.assertEqual(rec["status"], "announcement")
        self.assertEqual(rec["body"], "memo body")
        # the record schema is fixed: arbitrary extra frontmatter keys are
        # file-local only (code behavior, not a bug)
        self.assertNotIn("type", rec)

    # -- 5. long body renders in FULL at the renderer level -----------------

    def test_long_body_full_at_record_level(self):
        text = "z" * 600
        _seq, path = self._post(text, sender="alice")
        rec = self._record(path)
        self.assertEqual(rec["body"], text)
        self.assertEqual(len(rec["body"]), 600)

    # -- 6. raw HTML: canonical behavior is passthrough ---------------------

    def test_raw_html_passthrough(self):
        html = ("<b>bold</b> <i>ital</i> <a href=\"https://x.test\">l</a> "
                "<script>alert('x')</script> <style>p{color:red}</style>")
        _seq, path = self._post(html, sender="alice")
        rec = self._record(path)
        # canonical: the feed API neither escapes nor sanitizes the body;
        # first-class HTML/CSS rendering is the client's job (Vex's lane),
        # which requires the server to pass the body through untouched.
        self.assertEqual(rec["body"], html)
        self.assertNotIn("&lt;", rec["body"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
