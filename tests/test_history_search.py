#!/usr/bin/env python3
"""Tests for history_search.py.

Builds a fixture squawk root (frontmatter+body messages, a .bak decoy,
a malformed file) and asserts parsing, all filters, query modes, limit
bounding, and JSON output.
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

_here = os.path.dirname(os.path.abspath(__file__))
for _cand in (_here, os.path.join(_here, "..")):
    if os.path.exists(os.path.join(_cand, "history_search.py")):
        sys.path.insert(0, _cand)
        break
import history_search as hs


def msg(seq, sender, channel, ts, title, body, status="discussion"):
    return ("---\nseq: %d\nfrom: %s\nto: all\nchannel: %s\n"
            "ts: %s\nstatus: %s\ntitle: %s\nlamport: %d\nparents: []\n"
            "hmac: deadbeef\n---\n%s\n"
            % (seq, sender, channel, ts, status, title, seq, body))


def fixture_root():
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "fleet"))
    os.makedirs(os.path.join(root, "leads"))
    files = {
        "fleet/0001.md": msg(1, "shingle", "fleet",
                             "2026-09-14T13:47:12-06:00", "bootstrap",
                             "squawk bootstrap complete: fleet channel live"),
        "fleet/0002.md": msg(2, "ember", "fleet",
                             "2026-09-20T10:00:00-06:00", "race notes",
                             "the keypool race won by fast key", "shipped"),
        "fleet/0003.md": msg(3, "ember", "fleet",
                             "2026-09-20T11:00:00-06:00", "hedge",
                             "hedged launch: backups fire at 150ms"),
        "leads/0004.md": msg(4, "shingle", "leads",
                             "2026-09-20T12:00:00-06:00", "lead",
                             "new lead about the big race"),
        "fleet/0005.md.bak": msg(5, "ember", "fleet",
                                 "2026-09-20T13:00:00-06:00", "decoy",
                                 "this backup must never be scanned"),
        "fleet/bad.md": "no frontmatter here at all\njust text\n",
    }
    for rel, content in files.items():
        with open(os.path.join(root, rel), "w") as f:
            f.write(content)
    return root


def run(root, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = hs.main(["--root", root] + list(argv))
    assert rc == 0
    return buf.getvalue()


def test_parsing_and_query():
    root = fixture_root()
    out = run(root, "--json", "race")
    recs = [json.loads(l) for l in out.splitlines()]
    seqs = sorted(r["seq"] for r in recs)
    assert seqs == ["2", "4"], seqs  # title+body substring, case-insensitive
    r2 = [r for r in recs if r["seq"] == "2"][0]
    assert r2["from"] == "ember" and r2["channel"] == "fleet"
    assert "fast key" in r2["snippet"]
    print("PASS test_parsing_and_query")


def test_bak_and_malformed_skipped():
    root = fixture_root()
    out = run(root, "--json")
    recs = [json.loads(l) for l in out.splitlines()]
    seqs = sorted(r["seq"] for r in recs)
    assert "5" not in seqs, seqs  # .bak not scanned
    assert len(recs) == 4, recs   # bad.md skipped
    print("PASS test_bak_and_malformed_skipped")


def test_filters():
    root = fixture_root()
    assert len([json.loads(l) for l in
                run(root, "--json", "--channel", "leads").splitlines()]) == 1
    recs = [json.loads(l) for l in
            run(root, "--json", "--from", "ember").splitlines()]
    assert sorted(r["seq"] for r in recs) == ["2", "3"], recs
    recs = [json.loads(l) for l in
            run(root, "--json", "--status", "shipped").splitlines()]
    assert [r["seq"] for r in recs] == ["2"], recs
    recs = [json.loads(l) for l in
            run(root, "--json", "--seq-min", "2", "--seq-max", "3").splitlines()]
    assert sorted(r["seq"] for r in recs) == ["2", "3"], recs
    recs = [json.loads(l) for l in run(
        root, "--json", "--since", "2026-09-20T10:30:00-06:00",
        "--until", "2026-09-20T11:30:00-06:00").splitlines()]
    assert [r["seq"] for r in recs] == ["3"], recs
    # combined filters AND together
    recs = [json.loads(l) for l in run(
        root, "--json", "--channel", "fleet", "--from", "ember",
        "hedged").splitlines()]
    assert [r["seq"] for r in recs] == ["3"], recs
    print("PASS test_filters")


def test_regex_and_limit():
    root = fixture_root()
    recs = [json.loads(l) for l in
            run(root, "--json", "--regex", r"backups? fire").splitlines()]
    assert [r["seq"] for r in recs] == ["3"], recs
    recs = [json.loads(l) for l in
            run(root, "--json", "--limit", "2").splitlines()]
    assert [r["seq"] for r in recs] == ["1", "2"], recs  # seq order, bounded
    print("PASS test_regex_and_limit")


def test_human_output():
    root = fixture_root()
    out = run(root, "bootstrap")
    assert "[1] fleet <shingle>" in out and "bootstrap complete" in out, out
    print("PASS test_human_output")


if __name__ == "__main__":
    test_parsing_and_query()
    test_bak_and_malformed_skipped()
    test_filters()
    test_regex_and_limit()
    test_human_output()
    print("ALL SEARCH TESTS PASS")
