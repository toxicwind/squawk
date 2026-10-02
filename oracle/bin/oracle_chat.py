#!/usr/bin/python3
"""oracle-chat: the oracle lives in the chat.

Pitchfork-managed daemon (sovereign/oracle-chat). Watches the squawk
fleet + leads channels via inotify (ctypes, stdlib-only -- pattern borrowed
from oracle_loop.py) and participates as `from: oracle`.

Behavior:
  - Trigger: a message whose body starts with "oracle:" (case-insensitive)
    or contains "@oracle". Own messages (from: oracle) are never answered.
  - Questions / predictions -> POST /ask to oracle-core (127.0.0.1:25151).
    Ack immediately in-chat, run the ask in a background thread (debate-tier
    asks can take ~150s), post the verdict when it lands.
  - Work requests -> the REAL intake path: an intake_request posted to the
    bid-market channel via bidder.SeqPoster (exactly like post_intake.py),
    then the ledger is watched for the triage decision and the route is
    reported back in chat.
  - Loop prevention (load-bearing): own-message filter + per-channel
    high-water watermark + persisted replied-seq set. A reply storm in
    fleet is a failure.

Touches: its own state file (work/oracle-chat.state) and its own outbound
squawk messages. Never touches credentials, the control key, judges,
calibration, or the market loop. Read-only on everything else.

Event-driven throughout: the main loop is select() on inotify fds.
No timers, no polling.
"""

import base64
import ctypes
import fcntl
import importlib.util
import json
import os
import re
import select
import struct
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
AGENT_DIR = BIN.parent

SQUAWK_ROOT = Path(os.environ.get("ORACLE_SQUAWK_ROOT",
                                  "/home/toxic/.fleet-bus/squawk-root"))
CHANNELS = [c for c in os.environ.get("ORACLE_CHAT_CHANNELS", "fleet,leads").split(",") if c]
BID_MARKET = Path(os.environ.get("ORACLE_CHANNEL",
                                 "/home/toxic/.fleet-bus/squawk-root/bid-market"))
ORACLE_CORE = os.environ.get("ORACLE_CORE_URL", "http://127.0.0.1:25151")
LEDGER = Path(os.environ.get("ORACLE_LEDGER",
                             str(AGENT_DIR / "ledger" / "ledger.jsonl")))
STATE = Path(os.environ.get("ORACLE_CHAT_STATE",
                            str(AGENT_DIR / "work" / "oracle-chat.state")))
LOGF = Path(os.environ.get("ORACLE_CHAT_LOG",
                           str(AGENT_DIR / "work" / "oracle-chat.log")))
FROM = "oracle"

# ---------------- inotify (ctypes, stdlib only; borrowed from oracle_loop.py) --
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_MODIFY = 0x00000002

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.inotify_init1.argtypes = [ctypes.c_int]
_libc.inotify_init1.restype = ctypes.c_int
_libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
_libc.inotify_add_watch.restype = ctypes.c_int


def inotify_init(path, mask=None):
    if mask is None:
        mask = IN_CLOSE_WRITE | IN_MOVED_TO
    fd = _libc.inotify_init1(0)
    if fd < 0:
        raise OSError("inotify_init1 failed")
    wd = _libc.inotify_add_watch(fd, str(path).encode(), mask)
    if wd < 0:
        raise OSError("inotify_add_watch failed for %s" % path)
    return fd


def inotify_names(fd, want_modify=False):
    """Non-blocking drain; returns filenames with close_write/moved_to
    (or modify events when want_modify)."""
    out = []
    while True:
        r, _, _ = select.select([fd], [], [], 0)
        if not r:
            break
        data = os.read(fd, 65536)
        i = 0
        while i + 16 <= len(data):
            wd, mask, cookie, ln = struct.unpack("iIII", data[i:i + 16])
            name = data[i + 16:i + 16 + ln].split(b"\0", 1)[0].decode("utf-8", "replace")
            i += 16 + ln
            if want_modify:
                if mask & IN_MODIFY:
                    out.append(name)
            elif mask & (IN_CLOSE_WRITE | IN_MOVED_TO) and name.endswith(".md"):
                out.append(name)
    return out


# ---------------- basics ----------------------------------------------------
def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg)
    try:
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        with open(LOGF, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


SEQ_RE = re.compile(r"^(\d+)-")


def parse_msg(path):
    """Returns (frontmatter dict, body) or None."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm, body = parts[1], parts[2]
    meta = {}
    for line in fm.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body.strip()


def current_max_seq(channel):
    d = SQUAWK_ROOT / channel
    try:
        files = [f for f in os.listdir(d) if SEQ_RE.match(f)]
    except OSError:
        return 0
    return max([int(SEQ_RE.match(f).group(1)) for f in files] or [0])


# ---------------- state -----------------------------------------------------
_state_lock = threading.Lock()


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"watermarks": {}, "replied": [], "hello_posted": False}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.rename(tmp, STATE)


# ---------------- publishing (flock + atomic seq, same as squawk CLI) --------
def publish(channel, text, title=""):
    ts = datetime.now(timezone.utc).isoformat()
    slug = "".join(c if c.isalnum() else "-" for c in title[:30].lower()).strip("-") or "msg"
    content = (
        "---\n"
        "seq: @SEQ@\n"
        "from: %s\n"
        "to: all\n"
        "channel: %s\n"
        "ts: %s\n"
        "status: discussion\n"
        "title: %s\n"
        "---\n"
        "%s\n" % (FROM, channel, ts, title or slug, text)
    )
    chdir = SQUAWK_ROOT / channel
    chdir.mkdir(parents=True, exist_ok=True)
    lockpath = SQUAWK_ROOT / (".seq-%s.lock" % channel)
    with open(lockpath, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            seq = current_max_seq(channel) + 1
            fname = "%d-oracle-%s.md" % (seq, slug)
            (chdir / fname).write_text(content.replace("@SEQ@", str(seq)),
                                       encoding="utf-8")
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)
    return seq


# ---------------- trigger / routing -----------------------------------------
def extract_query(meta, body):
    """Return the addressed query text, or None if not for the oracle.

    Address forms: a leading "oracle:" or "oracle," (colon/comma required --
    a bare "oracle <word>" is someone labeling text ABOUT the oracle, e.g.
    "oracle note: ...", not addressing it), or an @oracle mention anywhere.
    """
    if meta.get("from", "").strip().lower() == FROM:
        return None  # own message -- never reply
    m = re.sub(r"^\s*oracle\s*[:,]\s*", "", body, flags=re.I)
    if m != body:
        q = m.strip()
    elif "@oracle" in body.lower():
        q = re.sub(r"@oracle\b", "", body, flags=re.I).strip(" :,-\n")
    else:
        return None
    return q or None


WORK_WORDS = ("fix", "build", "make", "do", "deploy", "commit", "push",
              "investigate", "audit", "research", "survey", "check", "probe",
              "test", "write", "create", "update", "upgrade", "restart",
              "kill", "stop", "start", "add", "remove", "delete", "refactor",
              "migrate", "file", "open")


def is_work(query):
    ql = query.strip().lower()
    if ql.endswith("?"):
        return False
    first = re.split(r"\s+", ql, 1)[0].strip("!.,")
    return first in WORK_WORDS


HELLO = ("the oracle is in the chat. Ask me anything "
         "(`oracle: will the herd stay green through the night?`) and I'll "
         "consult the judges; hand me work (`oracle: fix the flaky probe`) "
         "and I'll file it with the market. Terse by nature, oracular by design.")

NUDGE = ("I'm here. Ask me a question (`oracle: will X happen?`) or hand me "
         "work (`oracle: do Y`).")


def gloss(q):
    return " ".join(q.split()[:5])


# ---------------- ask path --------------------------------------------------
def format_verdict(question, v):
    status = v.get("status")
    if status == "refused":
        return ("I can't answer that yet -- %s"
                % v.get("clarification_request", "needs clarification."))
    p = v.get("probability")
    ptxt = ("p=%.3f" % p) if isinstance(p, (int, float)) else "p=?"
    line = ("**%s**\n%s · tier=%s · %.0fs · $%.4f"
            % (question[:160], ptxt, v.get("tier", "?"),
               v.get("latency_s", 0) or 0, v.get("cost_usd", 0) or 0))
    if status == "escalate":
        line += "\nEscalated -- %s" % v.get("tier_reason", "needs a human.")
    return line


def do_ask(channel, question):
    publish(channel, "on it -- %s..." % gloss(question), title="ack")
    try:
        payload = json.dumps({"question": question, "timeout_s": 240,
                              "allow_debate": True}).encode()
        req = urllib.request.Request(
            ORACLE_CORE + "/ask", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            verdict = json.loads(resp.read().decode())
        publish(channel, format_verdict(question, verdict), title="verdict")
    except Exception as e:  # noqa: BLE001 -- chat must never die on an ask
        log("ask failed: %r" % e)
        publish(channel,
                "the judges are silent (%s) -- try again in a bit." % e,
                title="ask failed")


# ---------------- intake path (the real front door) -------------------------
def _bidder():
    spec = importlib.util.spec_from_file_location("bidder", BIN / "bidder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wait_for_triage(frm, text, post_ts, timeout=45):
    """Watch the ledger for the triage decision matching this intake."""
    want_request = text[:500]
    try:
        fd = inotify_init(LEDGER, mask=IN_MODIFY)
    except OSError as e:
        log("ledger watch failed: %r" % e)
        return None
    try:
        off = LEDGER.stat().st_size if LEDGER.exists() else 0
    except OSError:
        off = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], max(0, deadline - time.time()))
        if not r:
            break
        inotify_names(fd, want_modify=True)  # drain
        try:
            with open(LEDGER, encoding="utf-8") as f:
                f.seek(off)
                chunk = f.read()
                off = f.tell()
        except OSError:
            continue
        for line in chunk.splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if (d.get("event") == "intake-decision"
                    and d.get("from") == frm
                    and d.get("request") == want_request
                    and d.get("ts", 0) >= post_ts - 1):
                return d
    return None


def do_intake(channel, frm, text):
    publish(channel, "filing it with the market -- one breath...",
            title="ack")
    try:
        bidder = _bidder()
        poster = bidder.SeqPoster(str(BID_MARKET), "bid-market", frm)
        post_ts = time.time()
        name = poster.post(
            "intake_request", "intake-%d" % int(post_ts),
            {"text": text, "posted_ts": post_ts},
            note="intake request from %s via oracle-chat" % frm)
        log("posted %s to bid-market" % name)
    except Exception as e:  # noqa: BLE001
        log("intake post failed: %r" % e)
        publish(channel, "couldn't file that with the market (%s)." % e,
                title="intake failed")
        return
    d = wait_for_triage(frm, text, post_ts)
    if not d:
        publish(channel,
                "filed with the market; triage is pending -- watch bid-market.",
                title="intake")
        return
    route, reason = d.get("route"), d.get("reason", "")
    if route == "TASK":
        msg = ("triaged **TASK** (%s) -- the auction opens in bid-market."
               % reason)
    elif route == "REJECT":
        msg = "the market declines -- **REJECT** (%s)." % reason
    else:
        msg = "triaged **%s** (%s)." % (route, reason)
    publish(channel, msg, title="intake")


# ---------------- main ------------------------------------------------------
def handle_file(channel, name, state):
    parsed = parse_msg(SQUAWK_ROOT / channel / name)
    if not parsed:
        return
    meta, body = parsed
    m = SEQ_RE.match(name)
    seq = int(m.group(1)) if m else 0
    with _state_lock:
        wm = state["watermarks"].get(channel, 0)
        if seq <= wm or seq in state["replied"]:
            if seq > wm:
                state["watermarks"][channel] = seq
                save_state(state)
            return
        state["watermarks"][channel] = max(wm, seq)
    query = extract_query(meta, body)
    if query is None:
        with _state_lock:
            save_state(state)
        return
    frm = meta.get("from", "?")
    log("trigger seq=%d from=%s q=%r" % (seq, frm, query[:80]))
    if len(query.split()) < 2:
        publish(channel, NUDGE, title="nudge")
    elif is_work(query):
        threading.Thread(target=do_intake, args=(channel, frm, query),
                         daemon=True).start()
    else:
        threading.Thread(target=do_ask, args=(channel, query),
                         daemon=True).start()
    with _state_lock:
        state["replied"].append(seq)
        state["replied"] = state["replied"][-500:]
        save_state(state)


def main():
    fresh = not STATE.exists()
    state = load_state()
    for ch in CHANNELS:
        (SQUAWK_ROOT / ch).mkdir(parents=True, exist_ok=True)
        state["watermarks"][ch] = max(state["watermarks"].get(ch, 0),
                                     current_max_seq(ch))
    if fresh and not state.get("hello_posted"):
        try:
            publish("fleet", HELLO, title="hello")
            state["hello_posted"] = True
            log("hello posted")
        except Exception as e:  # noqa: BLE001
            log("hello failed: %r" % e)
    save_state(state)
    fds = {}
    for ch in CHANNELS:
        fds[inotify_init(SQUAWK_ROOT / ch)] = ch
    log("oracle-chat live, watching %s" % ",".join(CHANNELS))
    while True:
        r, _, _ = select.select(list(fds), [], [], 3600)
        for fd in r:
            ch = fds[fd]
            for name in inotify_names(fd):
                try:
                    handle_file(ch, name, state)
                except Exception as e:  # noqa: BLE001 -- never die on one file
                    log("handle_file %s failed: %r" % (name, e))


if __name__ == "__main__":
    main()
