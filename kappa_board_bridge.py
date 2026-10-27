#!/usr/bin/env python3
"""kappa_board_bridge: mirror the kappa board table as a squawk chat channel.

Two-way, additive, idempotent bridge:

  board -> chat   reads new rows from `kappa_board_message` in the kappa
                  SQLite DB and writes one squawk message file per row
                  into <root>/<channel>/<seq>-<sender>-board.md.

  chat  -> board  reads squawk message files in <root>/<channel>/ and
                  inserts each new one into `kappa_board_message` on the
                  most-recently-updated `kappa_board` root, bumping the
                  board's next_seq / message_count counters.

It never deletes anything (reversible) and records a durable high-water
mark per direction in <channel>/.kappa-bridge-state.json so both loops are
safe to restart. Board-sourced files carry `source: kappa_board` frontmatter
so a later board->chat pass never re-imports its own writes.

Zero-dependency: Python stdlib only (sqlite3, pathlib, argparse), matching
the rest of squawk.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


STATE_FILENAME = ".kappa-bridge-state.json"
BOARD_SOURCE = "kappa_board"


def _frontmatter(path: Path) -> tuple[int, dict, str]:
    """Return (seq, frontmatter-dict, body) for a squawk .md message file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return 0, {}, ""
    fm: dict = {}
    body = raw
    if raw.startswith("---\n"):
        lines = raw.split("\n")
        close = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                close = i
                break
        if close is not None:
            body = "\n".join(lines[close + 1 :])
            for line in lines[1:close]:
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    try:
        seq = int(fm.get("seq") or path.name.split("-")[0])
    except ValueError:
        seq = 0
    return seq, fm, body


def _load_state(chan: Path) -> dict:
    p = chan / STATE_FILENAME
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(chan: Path, state: dict) -> None:
    (chan / STATE_FILENAME).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _active_board(db_path: Path) -> str | None:
    """Return the root_session_id of the most-recently-updated board (or None)."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = db.execute(
            "SELECT root_session_id FROM kappa_board ORDER BY time_updated DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def _board_rows(db_path: Path, since: int, root: str | None) -> list[tuple]:
    """Return board messages with seq > since as
    (seq, time_created, sender_session_id, recipient, type, body, id)."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        q = (
            "SELECT seq, time_created, sender_session_id, recipient, type, "
            "body, id FROM kappa_board_message WHERE seq > ?"
        )
        args: list = [since]
        if root is not None:
            q += " AND board_root_session_id = ?"
            args.append(root)
        q += " ORDER BY seq ASC"
        return db.execute(q, args).fetchall()
    finally:
        db.close()


def _row_to_file(chan: Path, row: tuple) -> Path:
    seq, ts, sender, _recipient, mtype, body, _mid = row
    slug = "".join(c if c.isalnum() else "-" for c in str(sender)[:20]).lower()
    slug = slug or "board"
    fpath = chan / f"{seq}-{slug}-board.md"
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts / 1000))
    fm = (
        "---\n"
        f"seq: {seq}\n"
        f"from: {sender}\n"
        "to: all\n"
        f"channel: kappa_board\n"
        f"ts: {ts_iso}\n"
        "status: discussion\n"
        f"source: {BOARD_SOURCE}\n"
        f"board_type: {_frontmatter_value(mtype)}\n"
        "title: board\n"
        "---\n"
        f"{body.rstrip()}\n"
    )
    fpath.write_text(fm, encoding="utf-8")
    return fpath


def _frontmatter_value(value) -> str:
    return " ".join(str(value).split())


def sync_board_to_chat(chan: Path, db_path: Path, root: str | None) -> int:
    """Mirror new board rows into the channel. Returns files written."""
    state = _load_state(chan)
    cursor = int(state.get("board_chat_cursor", 0))
    written = 0
    for row in _board_rows(db_path, cursor, root):
        seq = int(row[0])
        if seq <= cursor:
            continue
        _row_to_file(chan, row)
        written += 1
        cursor = max(cursor, seq)
    state["board_chat_cursor"] = cursor
    _save_state(chan, state)
    return written


def _chat_files(chan: Path) -> list[tuple[int, Path]]:
    out = []
    try:
        entries = list(os.scandir(chan))
    except OSError:
        return out
    for e in entries:
        if not e.name.endswith(".md"):
            continue
        seq, fm, _body = _frontmatter(Path(e.path))
        if seq <= 0 or fm.get("source") == BOARD_SOURCE:
            continue
        out.append((seq, Path(e.path)))
    return sorted(out, key=lambda t: t[0])


def _insert_into_board(
    db_path: Path, root: str, seq: int, ch_name: str, text: str
) -> None:
    row_id = f"msg_{seq}_bridge_{int(time.time() * 1000)}"
    ts = int(time.time() * 1000)
    db = sqlite3.connect(db_path)
    try:
        db.execute(
            "INSERT INTO kappa_board_message ("
            "id, board_root_session_id, seq, time_created, sender_session_id, "
            "recipient, type, body, reply_to, source_message_id, source_call_id"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                row_id,
                root,
                seq,
                ts,
                root,
                "all",
                "message",
                text,
                None,
                f"squawk:{ch_name}",
                "kappa_board_bridge",
            ),
        )
        db.execute(
            "UPDATE kappa_board SET next_seq = MAX(next_seq, ? + 1), "
            "message_count = message_count + 1, "
            "message_bytes = message_bytes + ?, "
            "time_updated = ? WHERE root_session_id = ?",
            (seq, len(text.encode("utf-8")), ts, root),
        )
        db.commit()
    finally:
        db.close()


def sync_chat_to_board(chan: Path, db_path: Path, root: str | None) -> int:
    """Mirror new chat messages into the board. Returns rows inserted."""
    state = _load_state(chan)
    cursor = int(state.get("chat_board_cursor", 0))
    if root is None:
        return 0
    inserted = 0
    for seq, path in _chat_files(chan):
        if seq <= cursor:
            continue
        _seq, _fm, body = _frontmatter(path)
        if not body.strip():
            continue
        _insert_into_board(db_path, root, seq, chan.name, body.strip())
        cursor = max(cursor, seq)
        inserted += 1
    state["chat_board_cursor"] = cursor
    _save_state(chan, state)
    return inserted


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        default=os.environ.get("AGENT_CHAT_ROOT")
        or str(Path.home() / ".fleet-bus" / "squawk-root"),
        help="squawk chat root (default: ~/.fleet-bus/squawk-root)",
    )
    ap.add_argument(
        "--db",
        default=os.path.expanduser("~/.local/share/kappa/kappa-main.db"),
        help="kappa SQLite DB path",
    )
    ap.add_argument("--channel", default="kappa_board", help="channel to mirror")
    ap.add_argument(
        "--root-session",
        default=None,
        help="kappa_board root_session_id to target (default: newest)",
    )
    ap.add_argument(
        "--watch",
        action="store_true",
        help="poll forever (default: single two-way sync pass, then exit)",
    )
    args = ap.parse_args(argv)

    chan = Path(args.root) / args.channel
    db_path = Path(args.db)
    if not chan.is_dir():
        print(
            f"error: channel '{chan}' not found (run: chat.py init {args.channel})",
            file=sys.stderr,
        )
        return 2
    if not db_path.is_file():
        print(f"error: kappa DB '{db_path}' not found", file=sys.stderr)
        return 2

    root = args.root_session or _active_board(db_path)

    def one_pass():
        to_chat = sync_board_to_chat(chan, db_path, root)
        to_board = sync_chat_to_board(chan, db_path, root)
        if to_chat or to_board:
            print(f"board->chat: {to_chat}  chat->board: {to_board}")

    if args.watch:
        while True:
            one_pass()
            time.sleep(3)
    one_pass()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
