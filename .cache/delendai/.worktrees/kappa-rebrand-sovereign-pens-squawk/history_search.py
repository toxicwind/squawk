#!/usr/bin/env python3
"""squawk history search: search squawk message history (metadata + body).

Reads squawk message files (YAML frontmatter + markdown body) under a
squawk root (default $SQUAWK_CHAT_ROOT or ~/.fleet-bus/squawk-root) and
returns matching messages. Pure batch CLI — no daemon, no polling loop.

Usage:
    history_search.py [QUERY] [--channel fleet] [--from ember]
        [--seq-min 100] [--seq-max 200] [--since 2026-09-20T00:00-06:00]
        [--until 2026-09-21T00:00-06:00] [--status discussion]
        [--regex] [--limit 50] [--json] [--root PATH]

Filters combine (AND). Results are bounded by --limit (default 50) and
sorted by global seq ascending.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

DEFAULT_ROOT = os.environ.get(
    "SQUAWK_CHAT_ROOT",
    os.path.expanduser("~/.fleet-bus/squawk-root"))
DEFAULT_LIMIT = 50
SNIPPET_LEN = 200


def parse_frontmatter(text):
    """Minimal YAML-subset parser for squawk frontmatter (key: value, inline [])."""
    meta = {}
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            meta[k] = [x.strip() for x in inner.split(",")] if inner else []
        else:
            meta[k] = v
    return meta, text[end + 4:].lstrip("\n")


def parse_ts(ts):
    if ts is None:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def iter_messages(root):
    """Yield (path, meta, body); warn and skip malformed files."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError as e:
                print("warn: cannot read %s: %s" % (path, e),
                      file=sys.stderr)
                continue
            parsed = parse_frontmatter(text)
            if parsed is None:
                print("warn: no frontmatter in %s, skipping" % path,
                      file=sys.stderr)
                continue
            meta, body = parsed
            yield path, meta, body


def match(meta, body, args, matcher):
    if args.channel and meta.get("channel") not in args.channel:
        return False
    if args.sender and meta.get("from") != args.sender:
        return False
    if args.status and meta.get("status") != args.status:
        return False
    try:
        seq = int(meta.get("seq", -1))
    except (TypeError, ValueError):
        seq = -1
    if args.seq_min is not None and seq < args.seq_min:
        return False
    if args.seq_max is not None and seq > args.seq_max:
        return False
    if args.since is not None or args.until is not None:
        ts = parse_ts(meta.get("ts"))
        if ts is None:
            return False
        if args.since is not None and ts < args.since:
            return False
        if args.until is not None and ts > args.until:
            return False
    if matcher and not matcher(meta, body):
        return False
    return True


def snippet(body, query, use_regex):
    if not query:
        return body[:SNIPPET_LEN].replace("\n", " ")
    if use_regex:
        m = re.search(query, body, re.IGNORECASE)
    else:
        i = body.lower().find(query.lower())
        m = None if i == -1 else (i, i + len(query))
    if m is None:
        return body[:SNIPPET_LEN].replace("\n", " ")
    start = m.start() if hasattr(m, "start") else m[0]
    lo = max(0, start - 60)
    return ("…" if lo else "") + body[lo:lo + SNIPPET_LEN].replace("\n", " ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Search squawk message history.")
    ap.add_argument("query", nargs="?", default=None,
                    help="substring (or regex with --regex) over title+body")
    ap.add_argument("--channel", action="append", default=[],
                    help="channel filter (repeatable)")
    ap.add_argument("--from", dest="sender", default=None,
                    help="sender filter")
    ap.add_argument("--status", default=None, help="status filter")
    ap.add_argument("--seq-min", type=int, default=None)
    ap.add_argument("--seq-max", type=int, default=None)
    ap.add_argument("--since", default=None, help="ISO timestamp, inclusive")
    ap.add_argument("--until", default=None, help="ISO timestamp, inclusive")
    ap.add_argument("--regex", action="store_true")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--json", action="store_true",
                    help="JSONL records on stdout")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    args = ap.parse_args(argv)

    if args.since is not None:
        args.since = parse_ts(args.since)
        if args.since is None:
            ap.error("cannot parse --since")
    if args.until is not None:
        args.until = parse_ts(args.until)
        if args.until is None:
            ap.error("cannot parse --until")

    def matcher(meta, body):
        hay = (meta.get("title", "") + "\n" + body)
        if args.regex:
            return re.search(args.query, hay, re.IGNORECASE) is not None
        return args.query.lower() in hay.lower()

    use_matcher = matcher if args.query else None
    hits = []
    scanned = 0
    for path, meta, body in iter_messages(args.root):
        scanned += 1
        if match(meta, body, args, use_matcher):
            try:
                seq = int(meta.get("seq", 0))
            except (TypeError, ValueError):
                seq = 0
            hits.append((seq, path, meta, body))
    hits.sort(key=lambda h: h[0])
    total = len(hits)
    hits = hits[:args.limit]

    if args.json:
        for _seq, path, meta, body in hits:
            print(json.dumps({
                "seq": meta.get("seq"), "from": meta.get("from"),
                "to": meta.get("to"), "channel": meta.get("channel"),
                "ts": meta.get("ts"), "status": meta.get("status"),
                "title": meta.get("title"), "file": path,
                "snippet": snippet(body, args.query, args.regex),
            }))
    else:
        for _seq, path, meta, body in hits:
            print("[%s] %s <%s> %s — %s" % (
                meta.get("seq"), meta.get("channel"), meta.get("from"),
                meta.get("ts"), meta.get("title") or "(no title)"))
            print("    %s" % snippet(body, args.query, args.regex))
    print("(%d of %d matches shown; scanned %d files)" % (
        len(hits), total, scanned), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
