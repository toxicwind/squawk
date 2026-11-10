#!/usr/bin/env python3
"""squawk-ws: first-class websocket push feed for Squawk. Stdlib only.

Watches the live message sources with inotify (libc via ctypes) and pushes
new messages to subscribed websocket clients in real time. Replaces all
polling (vault pulls, long-poll, digest crons) for the Chris-facing feed.

Sources:
  - /home/toxic/.squawk-bus/squawk-root/<channel>/*.md  (chat.py channel files)
  - zipfs-vault local zip manifest (unsealed relay envelopes)

Protocol:
  - wss://host/squawk-ws  (behind Tailscale funnel; server binds 127.0.0.1)
  - Auth: `Authorization: Bearer <token>` header on the Upgrade request,
    or `?token=<token>` query param (browsers cannot set headers on
    WebSocket()). Constant-time compared against SQUAWK_WS_TOKEN_FILE
    plus the feed token file (unified web credential). No valid
    credential -> 401.
  - After 101, client sends {"subscribe": ["fleet","leads"]} (or nothing =
    all channels). Optional "since": <gseq> (or {"since": {"fleet": N, ...}})
    replays everything newer than that cursor -- outbox first, then disk
    via the durable file_seq->gseq map for cursors older than outbox
    retention. Server replays backlog oldest-first, then streams live
    messages as JSON text frames:
      {"seq": N, "file_seq": M, "channel": "fleet", "sender": "shingle",
       "text": "...", "ts": "...", "sealed": false}
    `seq` is the server-global monotonic cursor (use for `since`).
    `file_seq` is the durable per-channel file sequence from seq_alloc
    (survives restarts, merges, and reseeds; the stable cross-writer id).
    Sealed messages broadcast sender + sealed:true FLAG ONLY -- never
    content or ciphertext.
  - Slow consumers: if a client's queue (256) fills, the server closes the
    connection with WS code 1013 (try again later) instead of silently
    dropping. Reconnect with "since" to resume without loss.
  - Plain HTTP GET /ping -> {"ok": true, ...} (health check, no auth).

State: global monotonic seq + per-source cursors + file_seq->gseq map
persisted in SQUAWK_WS_STATE_DIR/state.json, so restarts never reset or
duplicate. The map is backfilled on first boot after upgrade (one-time
renumber of pre-map history); afterwards every file keeps a stable gseq.
"""

import asyncio
import signal
import base64
import ctypes
import ctypes.util
import hashlib
import hmac
import json
import os
import re
import struct
import threading
import zipfile
from pathlib import Path

PORT = int(os.environ.get("SQUAWK_WS_PORT", "25147"))
CHAT_ROOT = Path(
    os.environ.get("SQUAWK_CHAT_ROOT", "/home/toxic/.squawk-bus/squawk-root")
)
CHANNELS = [
    c for c in os.environ.get("SQUAWK_WS_CHANNELS", "fleet,leads").split(",") if c
]
VAULT_ZIP = Path(
    os.environ.get(
        "SQUAWK_WS_VAULT", "/home/toxic/workspace/skills/zipfs-vault/store/vault.zip"
    )
)
TOKEN_FILE = Path(
    os.environ.get("SQUAWK_WS_TOKEN_FILE", "/home/toxic/.squawk-ws-token")
)
FEED_TOKEN_FILE = Path(
    os.environ.get(
        "SQUAWK_WS_FEED_TOKEN_FILE", "/home/toxic/.squawk-bus/squawk-relay/feed-token"
    )
)
STATE_DIR = Path(os.environ.get("SQUAWK_WS_STATE_DIR", "/home/toxic/.squawk-ws"))
STATE_FILE = STATE_DIR / "state.json"
OUTBOX_KEEP = 200
BACKFILL_N = 20
REPLAY_MAX = 1000  # hard cap on a single since-replay, oldest-first
SLOW_CLOSE_CODE = 1013  # WS "try again later" -- slow consumer
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
MSG_FILE_RE = re.compile(r"^\d+-.*\.md$")
ALIAS_RE = re.compile(r"^(fleet|leads)/(\d+)$")

# ---------------- inotify (libc via ctypes, stdlib only) ----------------
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_NONBLOCK = 0o4000  # O_NONBLOCK

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def _check(ret, what):
    if ret < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, "%s: %s" % (what, os.strerror(errno)))
    return ret


_inotify_fd = _check(_libc.inotify_init1(IN_NONBLOCK), "inotify_init1")
_EVENT_FMT = "iIII"
_EVENT_SIZE = struct.calcsize(_EVENT_FMT)


def _add_watch(path, mask):
    return _check(
        _libc.inotify_add_watch(_inotify_fd, str(path).encode(), mask),
        "inotify_add_watch %s" % path,
    )


def _drain_events():
    events = []
    try:
        while True:
            data = os.read(_inotify_fd, 65536)
            if not data:
                break
            i = 0
            while i + _EVENT_SIZE <= len(data):
                wd, mask, _cookie, elen = struct.unpack_from(_EVENT_FMT, data, i)
                i += _EVENT_SIZE
                name = data[i : i + elen].split(b"\0", 1)[0].decode(errors="replace")
                i += elen
                events.append((wd, mask, name))
    except BlockingIOError:
        pass
    except OSError:
        pass
    return events


# ---------------- message parsing ----------------
def parse_msg_file(path):
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm, body = m.groups()
    meta = {}
    for line in fm.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    try:
        seq = int(meta.get("seq", 0))
    except ValueError:
        seq = 0
    sealed = meta.get("status", "") == "sealed"
    return {
        "msg_seq": seq,
        "channel": meta.get("channel", path.parent.name),
        "sender": meta.get("from", "unknown"),
        "ts": meta.get("ts", ""),
        "sealed": sealed,
        "text": "" if sealed else body.strip(),
    }


def _read_token_file(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def load_tokens():
    """All valid bearer tokens: the WS token file plus the feed token
    file. The feed token already grants full read access via the feed;
    accepting it here unifies the web credential so the UI (which holds
    the feed token) can use the WS without a second secret. Browsers
    cannot set Authorization headers on WebSocket(), so ?token= is also
    accepted (same magic-link pattern as the feed)."""
    toks = set()
    for path in (TOKEN_FILE, FEED_TOKEN_FILE):
        tok = _read_token_file(path)
        if tok:
            toks.add(tok)
    return toks


def load_token():
    toks = load_tokens()
    return next(iter(toks)) if toks else ""


# ---------------- shared state ----------------
_scan_lock = threading.Lock()

gseq = 0
chan_last = {}  # channel -> last msg_seq seen
vault_last = 0  # last vault alias seq seen
gseq_map = {}  # channel -> {str(file_seq): gseq}; durable cursor map
outbox = {}  # channel -> [broadcast msgs], oldest-first
subscribers = set()  # (asyncio.Queue, frozenset(channels), writer)
_dynamic_channels = set()  # channels discovered on disk beyond CHANNELS
# directories under the chat root that are NOT message channels
RESERVED_DIRS = {"keys", "presence"}  # not message channels (Pry, 2026-10-19)
_watched_dirs = set()  # str paths with an inotify watch installed
_loop = None  # event loop, set in main() for cross-thread close
_state_dirty = False


def all_channels():
    return list(CHANNELS) + sorted(_dynamic_channels)


def _map_get(ch, file_seq):
    return gseq_map.get(ch, {}).get(str(file_seq))


def _map_put(ch, file_seq, g):
    gseq_map.setdefault(ch, {})[str(file_seq)] = g


def load_state():
    global gseq, chan_last, vault_last, gseq_map
    try:
        s = json.loads(STATE_FILE.read_text())
        gseq = int(s.get("gseq", 0))
        chan_last = dict(s.get("chan", {}))
        vault_last = int(s.get("vault", 0))
        raw = s.get("gseq_map", {})
        gseq_map = {
            ch: {str(k): int(v) for k, v in m.items()}
            for ch, m in raw.items()
            if isinstance(m, dict)
        }
    except (OSError, ValueError):
        pass


def save_state():
    global _state_dirty
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "gseq": gseq,
                    "chan": chan_last,
                    "vault": vault_last,
                    "gseq_map": gseq_map,
                }
            )
        )
        tmp.replace(STATE_FILE)  # atomic: readers never see a half-write
        _state_dirty = False
    except OSError as e:
        print("state save failed: %s" % e, flush=True)


def _close_writer_slow(writer, peer):
    """Loop-thread close for a slow consumer: WS 1013 then TCP close."""
    try:
        writer.write(bytes([0x88, 0x02, 0x03, 0xF5]))  # close, code 1013
    except Exception:
        pass
    try:
        writer.close()
    except Exception:
        pass
    print("slow consumer %s closed (1013)" % (peer,), flush=True)


def _fanout(msg, targets):
    """Deliver one message to subscribed queues. Runs on the event loop
    thread (scheduled via call_soon_threadsafe) so put_nowait wakes
    getters promptly -- a bare cross-thread put_nowait can leave the
    loop asleep in select() and delay delivery up to the 30s ping."""
    for q, want, writer in targets:
        if msg["channel"] not in want:
            continue
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            # Slow consumer: close with 1013 so it can reconnect with
            # `since` and resume without loss. Discard now so we don't
            # keep scheduling closes for a dead connection.
            subscribers.discard((q, want, writer))
            _close_writer_slow(writer, writer.get_extra_info("peername"))


def publish(channel, sender, text, ts, sealed, file_seq=0):
    """Assign global seq, buffer, persist, broadcast. Returns the message."""
    global gseq, _state_dirty
    gseq += 1
    if file_seq:
        _map_put(channel, file_seq, gseq)
    msg = {
        "seq": gseq,
        "file_seq": file_seq,
        "channel": channel,
        "sender": sender,
        "ts": ts or "",
        "sealed": bool(sealed),
    }
    if not sealed:
        msg["text"] = text or ""
    buf = outbox.setdefault(channel, [])
    buf.append(msg)
    del buf[: max(0, len(buf) - OUTBOX_KEEP)]
    _state_dirty = True
    save_state()
    targets = list(subscribers)
    if _loop is not None:
        _loop.call_soon_threadsafe(_fanout, msg, targets)
    else:
        _fanout(msg, targets)
    print(
        "publish seq=%d file_seq=%d ch=%s from=%s sealed=%s"
        % (gseq, file_seq, channel, sender, sealed),
        flush=True,
    )
    return msg


# ---------------- source scanning ----------------
def _discover_channels():
    """Pick up channel dirs created after startup; watch them too."""
    try:
        names = [p.name for p in CHAT_ROOT.iterdir() if p.is_dir()]
    except OSError:
        return
    for name in names:
        if (
            name.startswith(".")
            or name.startswith("-")
            or name in CHANNELS
            or name in _dynamic_channels
            or name in RESERVED_DIRS
        ):
            continue
        _dynamic_channels.add(name)
        d = CHAT_ROOT / name
        key = str(d)
        if key not in _watched_dirs:
            try:
                _add_watch(d, IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE)
                _watched_dirs.add(key)
                print("discovered + watching channel %s" % d, flush=True)
            except OSError as e:
                print("watch failed for %s: %s" % (d, e), flush=True)


def scan_channels(initial=False):
    if not _scan_lock.acquire(blocking=False):
        return
    try:
        _discover_channels()
        _scan_channels_locked(initial)
    finally:
        _scan_lock.release()


def _scan_channels_locked(initial=False):
    global gseq
    for ch in all_channels():
        d = CHAT_ROOT / ch
        if not d.is_dir():
            continue
        last = chan_last.get(ch, 0)
        newest = last
        try:
            files = sorted(
                p for p in d.iterdir() if p.is_file() and MSG_FILE_RE.match(p.name)
            )
        except OSError:
            continue
        if initial:
            # Seed outbox with REAL gseqs. Files already in the durable
            # map keep their recorded gseq (stable across restarts);
            # pre-map history gets fresh gseqs once, then persists.
            for p in files:
                parsed = parse_msg_file(p)
                if not parsed:
                    continue
                fs = parsed["msg_seq"]
                g = _map_get(ch, fs)
                if g is None:
                    gseq += 1
                    g = gseq
                    _map_put(ch, fs, g)
                buf = outbox.setdefault(ch, [])
                m = {
                    "seq": g,
                    "file_seq": fs,
                    "channel": parsed["channel"],
                    "sender": parsed["sender"],
                    "ts": parsed["ts"],
                    "sealed": parsed["sealed"],
                }
                if not parsed["sealed"]:
                    m["text"] = parsed["text"]
                buf.append(m)
                newest = max(newest, fs)
            buf = outbox.get(ch)
            if buf:
                del buf[: max(0, len(buf) - OUTBOX_KEEP)]
            if newest != last:
                chan_last[ch] = newest
            _state_dirty = True
            continue
        for p in files:
            parsed = parse_msg_file(p)
            if not parsed or parsed["msg_seq"] <= last:
                continue
            newest = max(newest, parsed["msg_seq"])
            # Advance the in-memory cursor BEFORE publishing so a
            # concurrent or repeated scan of the same directory sees
            # the updated floor and skips the file. publish() persists
            # state, so chan_last is durable as soon as this line runs.
            chan_last[ch] = newest
            publish(
                parsed["channel"],
                parsed["sender"],
                parsed["text"],
                parsed["ts"],
                parsed["sealed"],
                file_seq=parsed["msg_seq"],
            )
        if newest != last:
            chan_last[ch] = newest
    if initial:
        save_state()


def scan_vault(initial=False):
    global vault_last
    if not _scan_lock.acquire(blocking=False):
        return
    try:
        _scan_vault_locked(initial)
    finally:
        _scan_lock.release()


def _scan_vault_locked(initial=False):
    global vault_last
    if not VAULT_ZIP.is_file():
        return
    try:
        with zipfile.ZipFile(VAULT_ZIP) as z:
            try:
                manifest = json.loads(z.read("manifest.json"))
            except KeyError:
                return
            items = []
            for alias, blob in manifest.items():
                m = ALIAS_RE.match(alias)
                if not m:
                    continue
                ch, num = m.group(1), int(m.group(2))
                if num <= vault_last:
                    continue
                try:
                    blob_name = blob["blob"] if isinstance(blob, dict) else blob
                    env = json.loads(z.read("blobs/" + blob_name))
                except (KeyError, ValueError):
                    continue
                items.append((num, ch, env))
    except (zipfile.BadZipFile, OSError):
        return
    if initial:
        if items:
            vault_last = max(n for n, _, _ in items)
        return
    for num, ch, env in sorted(items):
        sealed = bool(env.get("sealed", False))
        publish(
            ch, env.get("sender", "?"), env.get("text", ""), env.get("ts", ""), sealed
        )
        vault_last = max(vault_last, num)


def replay_since(want, since):
    """Messages with gseq > `since`, oldest-first, capped at REPLAY_MAX.

    `since` may be a single gseq (applies to all channels) or a dict
    {channel: gseq}. Outbox covers recent history; for cursors older than
    outbox retention we fall back to a disk scan via the durable
    file_seq->gseq map.
    """

    def cursor_for(ch):
        if isinstance(since, dict):
            try:
                return int(since.get(ch, 0))
            except (ValueError, TypeError):
                return 0
        try:
            return int(since)
        except (ValueError, TypeError):
            return 0

    out = []
    for ch in sorted(want):
        cur = cursor_for(ch)
        buf = outbox.get(ch, [])
        # Fast path: cursor inside outbox coverage.
        if buf and cur >= buf[0]["seq"]:
            out.extend(m for m in buf if m["seq"] > cur)
            continue
        # Slow path: cursor older than outbox (or outbox empty after a
        # restart) -- scan disk via the durable file_seq->gseq map.
        d = CHAT_ROOT / ch
        try:
            files = sorted(
                p for p in d.iterdir() if p.is_file() and MSG_FILE_RE.match(p.name)
            )
        except OSError:
            out.extend(m for m in buf if m["seq"] > cur)
            continue
        seen = set()
        for p in files:
            parsed = parse_msg_file(p)
            if not parsed:
                continue
            g = _map_get(ch, parsed["msg_seq"])
            if g is None or g <= cur:
                continue
            m = {
                "seq": g,
                "file_seq": parsed["msg_seq"],
                "channel": parsed["channel"],
                "sender": parsed["sender"],
                "ts": parsed["ts"],
                "sealed": parsed["sealed"],
            }
            if not parsed["sealed"]:
                m["text"] = parsed["text"]
            out.append(m)
            seen.add(parsed["msg_seq"])
        # live tail not yet on disk (skip file_seqs already covered above)
        out.extend(m for m in buf if m["seq"] > cur and m.get("file_seq") not in seen)
    out.sort(key=lambda m: m["seq"])
    return out[-REPLAY_MAX:]


# ---------------- websocket framing ----------------
def ws_accept(key):
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()


def ws_encode(payload: bytes):
    header = bytes([0x81])
    n = len(payload)
    if n < 126:
        header += bytes([n])
    elif n < 65536:
        header += bytes([126]) + struct.pack(">H", n)
    else:
        header += bytes([127]) + struct.pack(">Q", n)
    return header + payload


async def ws_read_frame(reader):
    hdr = await reader.readexactly(2)
    b1, b2 = hdr[0], hdr[1]
    fin = bool(b1 & 0x80)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if masked else None
    payload = await reader.readexactly(length) if length else b""
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, fin, payload


async def ws_read_message(reader):
    """Assemble fragmented text messages; answer pings; raise on close."""
    parts = []
    while True:
        opcode, fin, payload = await ws_read_frame(reader)
        if opcode == 0x8:
            raise ConnectionResetError("client close")
        if opcode == 0x9:
            yield ("ping", payload)
            continue
        if opcode == 0xA:
            continue
        if opcode == 0x1 or opcode == 0x0:
            parts.append(payload)
            if fin:
                yield ("text", b"".join(parts))
                parts = []
        # ignore other opcodes


# ---------------- connection handling ----------------
async def handle_client(reader, writer):
    peer = writer.get_extra_info("peername")
    try:
        # --- HTTP request ---
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=15)
            if not chunk:
                return
            raw += chunk
            if len(raw) > 65536:
                return
        head = raw.split(b"\r\n\r\n", 1)[0].decode("latin1")
        lines = head.split("\r\n")
        method, path = lines[0].split(" ", 2)[:2]
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        if method == "GET" and path.split("?")[0].rstrip("/").endswith("/ping"):
            body = json.dumps(
                {
                    "ok": True,
                    "seq": gseq,
                    "clients": len(subscribers),
                    "channels": all_channels(),
                    "high_water": {ch: chan_last.get(ch, 0) for ch in all_channels()},
                }
            ).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                b"Content-Length: "
                + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + body
            )
            await writer.drain()
            return

        # A websocket upgrade request (path /squawk-ws, /squawk-ws/ or the
        # tailscale prefix-stripped "/") must ALWAYS reach the WS handshake.
        # Never send a websocket client to the root redirect below.
        is_ws_upgrade = (
            headers.get("upgrade", "").lower() == "websocket"
            and "sec-websocket-key" in headers
        )

        if method == "GET" and not is_ws_upgrade:
            stripped = path.split("?")[0].rstrip("/")
            if (
                stripped in ("", "/")
                or stripped.endswith("/squawk-ws")
                or stripped == "/squawk-ws"
            ):
                # delend-controlled root redirect: entry point -> live ping instead of 404.
                target = os.environ.get("DELEND_SQUAWK_REDIRECT", "/ping")
                writer.write(
                    b"HTTP/1.1 302 Found\r\nLocation: "
                    + target.encode()
                    + b"\r\nConnection: close\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
                await writer.drain()
                return

        if not is_ws_upgrade:
            writer.write(
                b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n"
                b"Content-Length: 0\r\n\r\n"
            )
            await writer.drain()
            return

        # auth: Authorization: Bearer <t> header, or ?token=<t> query
        # (browsers cannot set headers on WebSocket()).
        toks = load_tokens()
        auth = headers.get("authorization", "")
        qtoken = ""
        if "?" in path:
            _qs = path.split("?", 1)[1]
            for _part in _qs.split("&"):
                if _part.startswith("token="):
                    qtoken = _part[6:]
                    break
        ok = False
        if toks:
            if auth.startswith("Bearer "):
                presented = auth[7:].strip()
                ok = any(hmac.compare_digest(presented, tok) for tok in toks)
            if not ok and qtoken:
                ok = any(hmac.compare_digest(qtoken, tok) for tok in toks)
        if not ok:
            writer.write(
                b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n"
                b"Content-Length: 0\r\n\r\n"
            )
            await writer.drain()
            print("auth rejected from %s" % (peer,), flush=True)
            return

        accept = ws_accept(headers["sec-websocket-key"])
        writer.write(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Accept: %s\r\n\r\n" % accept
            ).encode("latin1")
        )
        await writer.drain()

        # --- subscribe ---
        want = set(all_channels())
        since = 0
        try:
            async for kind, payload in ws_read_message(reader):
                if kind == "text":
                    try:
                        sub = json.loads(payload.decode("utf-8", "replace"))
                        chans = sub.get("subscribe", "all")
                        if chans != "all":
                            want = set(chans) & set(all_channels())
                        since = sub.get("since", 0)
                    except (ValueError, AttributeError):
                        pass
                    break
                # ignore pings pre-subscribe
        except (asyncio.TimeoutError, ConnectionResetError):
            return

        want = frozenset(want)  # tuple elements must be hashable
        q = asyncio.Queue(maxsize=256)
        subscribers.add((q, want, writer))
        print(
            "subscriber %s channels=%s since=%s" % (peer, sorted(want), since),
            flush=True,
        )
        try:
            # backfill: replay everything after `since` (since=0 means
            # recent history from disk, capped at REPLAY_MAX), oldest first
            backlog = replay_since(want, since)
            for m in backlog:
                writer.write(ws_encode(json.dumps(m).encode()))
            await writer.drain()

            async def sender():
                while True:
                    msg = await q.get()
                    writer.write(ws_encode(json.dumps(msg).encode()))
                    await writer.drain()

            async def pinger():
                while True:
                    await asyncio.sleep(30)
                    writer.write(bytes([0x89, 0x00]))  # ping, empty
                    await writer.drain()

            async def receiver():
                async for kind, payload in ws_read_message(reader):
                    if kind == "ping":
                        writer.write(bytes([0x8A, len(payload)]) + payload)
                        await writer.drain()

            await asyncio.wait(
                [
                    asyncio.create_task(sender()),
                    asyncio.create_task(pinger()),
                    asyncio.create_task(receiver()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            subscribers.discard((q, want, writer))
            print("subscriber %s gone" % (peer,), flush=True)
    except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
        pass
    except Exception as e:
        print("client error %s: %s" % (peer, e), flush=True)
    finally:
        try:
            writer.close()
        except Exception:
            pass


# ---------------- main ----------------
_rescan_scheduled = False


async def rescan():
    global _rescan_scheduled
    try:
        await asyncio.sleep(0.3)  # coalesce bursts
        await asyncio.get_running_loop().run_in_executor(None, do_rescan)
    finally:
        # Clear only after the scan completes, so events arriving during
        # the sleep or the executor call do not schedule concurrent rescans.
        _rescan_scheduled = False


def do_rescan():
    scan_channels()
    scan_vault()


def on_inotify():
    global _rescan_scheduled
    _drain_events()
    if not _rescan_scheduled:
        _rescan_scheduled = True
        asyncio.get_running_loop().create_task(rescan())


async def main():
    global _loop
    load_state()
    do_rescan()  # initial: seed outbox + cursors, no broadcast
    print("squawk-ws: initial scan done, gseq=%d" % gseq, flush=True)

    for ch in all_channels():
        d = CHAT_ROOT / ch
        if d.is_dir():
            try:
                _add_watch(d, IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE)
                _watched_dirs.add(str(d))
                print("watching %s" % d, flush=True)
            except OSError as e:
                print("watch failed for %s: %s" % (d, e), flush=True)
    if VAULT_ZIP.parent.is_dir():
        _add_watch(VAULT_ZIP.parent, IN_CLOSE_WRITE | IN_MOVED_TO)
        print("watching %s" % VAULT_ZIP.parent, flush=True)

    _loop = asyncio.get_running_loop()
    _loop.add_reader(_inotify_fd, on_inotify)

    server = await asyncio.start_server(
        handle_client, "127.0.0.1", PORT, reuse_port=True
    )
    print("squawk-ws listening on 127.0.0.1:%d" % PORT, flush=True)

    # Graceful shutdown on SIGTERM: stop accepting, finish in-flight,
    # then exit. For hot reload, the new process is already bound via
    # SO_REUSEPORT and serving.
    _shutdown = asyncio.Event()

    def _on_term():
        print("squawk-ws: SIGTERM, draining...", flush=True)
        _shutdown.set()

    _loop.add_signal_handler(signal.SIGTERM, _on_term)

    async with server:
        # Run until SIGTERM, then close gracefully
        await _shutdown.wait()
        server.close()
        await server.wait_closed()
        print("squawk-ws: drained, exiting", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
