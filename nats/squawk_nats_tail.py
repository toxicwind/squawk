#!/usr/bin/env python3
"""squawk-nats-tail: dual-publish tailer -- squawk file feed -> NATS + JetStream.

Every message file that lands in a watched channel dir (fleet, leads) is
parsed with the feed server's own tolerant parser and published to JetStream
on subject <channel>.messages as a JSON envelope. The file feed is untouched:
this tailer only READS. That is the whole migration strategy -- dual-publish
with no flag day; the custom feed server stays live as fallback.

Fail-open design (the legacy feed never blocks on NATS):
- The per-channel cursor (last-published seq) advances ONLY after the
  JetStream publish is ACKed. If NATS is down the tailer logs, backs off,
  and retries; on reconnect it catches up from the cursor. The file feed
  keeps serving the whole time.
- JetStream MsgId "squawk:<channel>:<seq>" dedups replays inside the
  duplicate window, so a tailer restart can never double-publish.
- Sealed messages publish metadata-only (body null, sealed true):
  ciphertext is never put on the wire, same as the feed server.

Subjects (dumb by design -- agent semantics come from A2A later, not from
subject-name cleverness):
  <channel>.messages        chat traffic, persisted in stream `squawk`
  <channel>.presence.<id>   ephemeral heartbeats (core NATS, NOT JetStream)
  KV bucket squawk_presence mirrors heartbeats for UI presence (TTL 120s)

Stream `squawk`: subjects [fleet.messages, leads.messages], file storage, retention limits
(100k msgs / 1GB / 90d, discard old) -- bounded, never a disk bomb.

Borrowed, not invented: _Inotify + _MSG_RE from squawk_feed.py (the same
watch the feed server uses), build_relay_record from fleet_relay.py (the
tolerant parser fixed in 48ff913b -- never raises on a bad message).
"""
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # squawk project dir
import fleet_relay
from squawk_feed import _Inotify, _MSG_RE

import nats

NATS_URL = os.environ.get("SQUAWK_NATS_URL", "nats://127.0.0.1:4222")
SQUAWK_ROOT = Path(os.environ.get("SQUAWK_ROOT", "/home/toxic/.fleet-bus/squawk-root"))
CHANNELS = [c.strip() for c in os.environ.get("SQUAWK_NATS_CHANNELS", "fleet,leads").split(",") if c.strip()]
AGENT = os.environ.get("SQUAWK_NATS_AGENT", "taps")
TOKEN_FILE_DEFAULT = str(Path.home() / ".fleet-bus" / "squawk-relay" / "feed-token")
STATE_DIR = Path(os.environ.get("SQUAWK_NATS_STATE_DIR",
                                "/home/toxic/.local/state/squawk-nats-tail"))
CURSOR_FILE = STATE_DIR / "cursor.json"

STREAM = "squawk"
KV_BUCKET = "squawk_presence"
HEARTBEAT_EVERY = 30.0
FALLBACK_SWEEP_EVERY = 60.0  # safety net for missed inotify events, not the mechanism


def _load_token() -> str:
    tok = os.environ.get("SQUAWK_FEED_TOKEN")
    if tok:
        return tok.strip()
    tf = os.environ.get("SQUAWK_FEED_TOKEN_FILE", TOKEN_FILE_DEFAULT)
    try:
        return Path(tf).read_text().strip()
    except OSError:
        raise SystemExit(f"squawk-nats-tail: no feed token at {tf}")


def _load_cursor() -> dict:
    try:
        return json.loads(CURSOR_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_cursor(cursor: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CURSOR_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cursor, indent=1))
    tmp.replace(CURSOR_FILE)


def _channel_high(chan_dir: Path) -> int:
    top = 0
    try:
        names = os.listdir(chan_dir)
    except OSError:
        return 0
    for name in names:
        m = _MSG_RE.match(name)
        if m:
            top = max(top, int(m.group(1)))
    return top


def _pending(chan_dir: Path, after_seq: int) -> list:
    """(seq, path) of message files newer than after_seq, oldest first."""
    hits = []
    try:
        names = os.listdir(chan_dir)
    except OSError:
        return []
    for name in names:
        m = _MSG_RE.match(name)
        if m:
            seq = int(m.group(1))
            if seq > after_seq:
                hits.append((seq, chan_dir / name))
    hits.sort(key=lambda t: (t[0], t[1].name))
    return hits


def _envelope(rec: dict) -> dict:
    """NATS envelope shaped for the Squawk UI's render(): from/channel/ts/
    title/body/sealed/signature/seq are exactly what ui.html already reads."""
    return {
        "v": 1,
        "seq": rec.get("seq", 0),
        "channel": rec.get("channel", ""),
        "from": rec.get("from", ""),
        "to": rec.get("to", "all"),
        "ts": rec.get("ts", ""),
        "title": rec.get("title", ""),
        "type": "msg",
        "sealed": bool(rec.get("sealed")),
        "signature": rec.get("signature", "invalid"),
        "body": rec.get("body"),  # None for sealed -- ciphertext never published
    }


async def _ensure_stream(js) -> None:
    try:
        await js.stream_info(STREAM)
        return
    except Exception:
        pass
    # NOTE: nats-server 2.14.5 rejects a leading-wildcard subject here
    # (overlap check vs the JetStream API); explicit per-channel subjects.
    subjects = [f"{c}.messages" for c in CHANNELS]
    await js.add_stream(
        name=STREAM,
        subjects=subjects,
        retention="limits",
        max_msgs=100_000,
        max_bytes=1_073_741_824,   # 1 GB
        max_age=90 * 24 * 3600,    # 90 days
        storage="file",
        discard="old",
        duplicate_window=3600,
        num_replicas=1,
    )
    print(f"squawk-nats-tail: created JetStream stream {STREAM}", flush=True)


async def _ensure_kv(js):
    try:
        return await js.create_key_value(bucket=KV_BUCKET, history=1, ttl=120)
    except Exception:
        return await js.key_value(KV_BUCKET)


class Tailer:
    def __init__(self, nc, js, kv, token):
        self.nc = nc
        self.js = js
        self.kv = kv
        self.cursor = _load_cursor()
        self.stop = asyncio.Event()
        # first run: cursor starts at the live high-water mark -- no ancient
        # backfill flood; JetStream history accumulates from here
        for ch in CHANNELS:
            if ch not in self.cursor:
                high = _channel_high(SQUAWK_ROOT / ch)
                self.cursor[ch] = high
                print(f"squawk-nats-tail: channel {ch}: cursor init at {high} (no backfill)",
                      flush=True)
        _save_cursor(self.cursor)

    async def publish_one(self, channel: str, seq: int, path: Path) -> bool:
        """Parse + publish one file. True only if the publish was ACKed."""
        try:
            rec = fleet_relay.build_relay_record(
                path, channel=channel, identity=AGENT,
                key_dir=SQUAWK_ROOT / "keys")
        except Exception as e:  # never let one bad file stall the lane
            print(f"squawk-nats-tail: parse failed {path.name}: {e} -- skipping",
                  flush=True)
            return True  # skip: cursor must advance past poison files
        env = _envelope(rec)
        env["seq"] = seq  # filename seq is canonical, always
        data = json.dumps(env, ensure_ascii=False).encode("utf-8")
        # nats-py 2.x dedups via the Nats-Msg-Id header (no msg_id kwarg)
        headers = {"Nats-Msg-Id": f"squawk:{channel}:{seq}"}
        try:
            await self.js.publish(f"{channel}.messages", data, headers=headers)
        except Exception as e:
            print(f"squawk-nats-tail: publish failed {channel}/{seq}: {e}",
                  flush=True)
            return False
        return True

    async def sweep(self, channel: str) -> None:
        chan_dir = SQUAWK_ROOT / channel
        if not chan_dir.is_dir():
            return
        for seq, path in _pending(chan_dir, self.cursor.get(channel, -1)):
            if self.stop.is_set():
                return
            ok = await self.publish_one(channel, seq, path)
            if not ok:
                return  # NATS down: keep cursor, retry on next sweep
            self.cursor[channel] = seq
            _save_cursor(self.cursor)

    async def sweep_all(self) -> None:
        for ch in CHANNELS:
            await self.sweep(ch)

    async def heartbeat(self) -> None:
        payload = json.dumps({
            "v": 1, "agent": AGENT, "lane": "nats-substrate",
            "ts": time.time(),
        }).encode()
        while not self.stop.is_set():
            try:
                await self.nc.publish(f"fleet.presence.{AGENT}", payload)
                await self.kv.put(AGENT, payload)
            except Exception as e:
                print(f"squawk-nats-tail: heartbeat failed: {e}", flush=True)
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=HEARTBEAT_EVERY)
            except asyncio.TimeoutError:
                pass

    async def fallback_sweeper(self) -> None:
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=FALLBACK_SWEEP_EVERY)
            except asyncio.TimeoutError:
                pass
            if self.stop.is_set():
                break
            await self.sweep_all()


async def _run() -> None:
    token = _load_token()
    backoff = 1.0
    while True:
        try:
            nc = await nats.connect(
                NATS_URL, token=token,
                max_reconnect_attempts=-1,  # daemon: never give up
                reconnect_time_wait=2.0,
            )
            break
        except Exception as e:
            print(f"squawk-nats-tail: connect failed ({e}), retry in {backoff:.0f}s",
                  flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
    print(f"squawk-nats-tail: connected to {NATS_URL}", flush=True)
    js = nc.jetstream()
    await _ensure_stream(js)
    kv = await _ensure_kv(js)

    tailer = Tailer(nc, js, kv, token)
    loop = asyncio.get_running_loop()
    watches = []
    for ch in CHANNELS:
        chan_dir = SQUAWK_ROOT / ch
        if not chan_dir.is_dir():
            print(f"squawk-nats-tail: no dir for channel {ch}, skipping watch",
                  flush=True)
            continue
        try:
            ino = _Inotify(chan_dir, 0x00000008 | 0x00000100)  # IN_CLOSE_WRITE|IN_MOVED_TO
        except OSError as e:
            print(f"squawk-nats-tail: inotify unavailable for {ch} ({e})", flush=True)
            continue
        watches.append((ch, ino))
        def _make_cb(channel, ino):
            def _cb():
                try:
                    ino.read_events()
                except OSError:
                    return
                asyncio.ensure_future(tailer.sweep(channel))
            return _cb
        loop.add_reader(ino.fd, _make_cb(ch, ino))
    print(f"squawk-nats-tail: watching {[c for c, _ in watches]}", flush=True)

    # catch anything that landed between cursor-init and watch-arm
    await tailer.sweep_all()

    hb = asyncio.ensure_future(tailer.heartbeat())
    fb = asyncio.ensure_future(tailer.fallback_sweeper())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, tailer.stop.set)
        except NotImplementedError:
            pass
    await tailer.stop.wait()

    hb.cancel(); fb.cancel()
    for _, ino in watches:
        try:
            loop.remove_reader(ino.fd)
            ino.close()
        except Exception:
            pass
    await nc.close()
    print("squawk-nats-tail: stopped clean", flush=True)


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
