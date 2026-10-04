#!/usr/bin/env python3
"""Shared helpers for the squawk relay (sink.py + forward.py). Stdlib only.

Paths resolve from env with the canonical shingle defaults; the reorg track
may move /home/toxic/.fleet-bus, so nothing here hardcodes beyond defaults.
"""
import ctypes
import ctypes.util
import fcntl
import hashlib
import json
import os
import select
import sys
from datetime import datetime, timezone
from pathlib import Path

RELAY_DIR = Path(os.environ.get("SQUAWK_RELAY_DIR", "/home/toxic/.fleet-bus/squawk-relay"))
CHAT_ROOT = Path(os.environ.get("SQUAWK_CHAT_ROOT", "/home/toxic/.fleet-bus/squawk-root"))
KEYS_DIR = Path(os.environ.get("FLEET_KEYS_DIR", str(CHAT_ROOT / "keys")))
SQUAWK_CODE = Path(os.environ.get("SQUAWK_CODE_DIR", "/home/toxic/squawk"))
CHAT_PY = SQUAWK_CODE / "chat.py"
OUTBOX = RELAY_DIR / "outbox.jsonl"
SINK_STATE = RELAY_DIR / "state.json"
FWD_STATE = RELAY_DIR / "forward-state.json"
CONTROL = RELAY_DIR / "control.json"
LOCK_FILE = RELAY_DIR / ".relay.lock"  # legacy; per-daemon locks below

# Process-lifetime lock handles. acquire_lock() stores the fh here so GC
# can never close it early: the flock must be held until process exit,
# otherwise two daemons race (and double-post). Callers must still keep
# using distinct names per daemon.
_HELD_LOCKS = {}
DEST_CHANNEL = os.environ.get("SQUAWK_RELAY_DEST", "fleet")
RELAY_IDENTITY = os.environ.get("SQUAWK_RELAY_IDENTITY", "relay")
MSG_FILE_RE = ".md"

WATCH_MASK = 0x00000008 | 0x00000100 | 0x40000000  # IN_CLOSE_WRITE|IN_MOVED_TO|IN_MODIFY


def log(msg):
    print("squawk-relay: %s" % msg, file=sys.stderr, flush=True)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def atomic_write_json(path, obj):
    """Crash-safe state write: tmp + fsync + rename + dir fsync."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    data = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    dirfd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def idempotency_key(channel, msg_seq, author, ts, body_sig):
    """Deterministic key: stable across re-ingests of the same source message.

    channel+msg_seq is unique per source message; the content hash guards
    against seq reuse with different content.
    """
    h = hashlib.sha1(("%s\n%s\n%s" % (author, ts, body_sig)).encode("utf-8")).hexdigest()[:12]
    return "relay:%s:%s:%s" % (channel, msg_seq, h)


def derive_key(entry):
    """Idempotency key for an outbox entry (explicit, else derived)."""
    if entry.get("idempotency_key"):
        return entry["idempotency_key"]
    return idempotency_key(
        entry.get("channel", "?"), entry.get("msg_seq", 0),
        entry.get("author", "?"), entry.get("ts", ""),
        entry.get("text", "")[:500])


def parse_ts(ts):
    """ISO ts -> epoch seconds (None on garbage). HFT hop math needs this."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return None


def hop_quantiles(samples, field):
    """p50/p95/max for one hop field over samples. None when empty."""
    vals = sorted(s[field] for s in samples if s.get(field) is not None)
    if not vals:
        return None

    def q(p):
        i = min(int(p * len(vals)), len(vals) - 1)
        return round(vals[i], 3)

    return {"n": len(vals), "p50": q(0.5), "p95": q(0.95), "max": round(vals[-1], 3)}


def acquire_lock(name):
    """Single-instance guard: exits 3 if another instance holds the lock.

    Per-daemon lock file (.sink.lock / .forward.lock) so the two relay
    halves never block each other. The handle is pinned in _HELD_LOCKS
    for the process lifetime: without this, CPython GC closes the fh
    immediately and the flock is silently released (this caused a real
    double-post: two forwarders racing the same outbox entry).
    """
    path = RELAY_DIR / (".%s.lock" % name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("%s: another instance holds the lock, exiting" % name)
        sys.exit(3)
    fh.write("%d %s %s\n" % (os.getpid(), name, now_iso()))
    fh.flush()
    _HELD_LOCKS[name] = fh  # pin: never GC, lock held until process exit
    return fh


class Inotify(object):
    """Minimal ctypes inotify wrapper (stdlib only)."""

    def __init__(self, paths, mask=WATCH_MASK):
        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        self._libc = ctypes.CDLL(libc_name, use_errno=True)
        self._libc.inotify_init1.argtypes = [ctypes.c_int]
        self._libc.inotify_init1.restype = ctypes.c_int
        self._libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._libc.inotify_add_watch.restype = ctypes.c_int
        fd = self._libc.inotify_init1(0)
        if fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        self.fd = fd
        os.set_blocking(fd, False)
        self._wds = []
        for p in paths:
            wd = self._libc.inotify_add_watch(fd, str(p).encode("utf-8"), ctypes.c_uint32(mask))
            if wd < 0:
                err = ctypes.get_errno()
                os.close(fd)
                raise OSError(err, "inotify_add_watch failed for %s" % p)
            self._wds.append(wd)

    def wait(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return False
        return bool(data)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def channel_dirs():
    """All channel dirs under CHAT_ROOT containing message files."""
    import re
    msg_re = re.compile(r"^\d+-.*\.md$")
    dirs = []
    if not CHAT_ROOT.is_dir():
        return dirs
    for d in sorted(CHAT_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            if any(f.is_file() and msg_re.match(f.name) for f in d.iterdir()):
                dirs.append(d)
        except OSError:
            continue
    return dirs
