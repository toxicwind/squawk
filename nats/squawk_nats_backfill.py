#!/usr/bin/env python3
"""squawk-nats-backfill: migrate the FULL squawk file-store history into JetStream.

The live tailer (squawk_nats_tail.py) only ever published files newer than its
first-run high-water mark, so the `squawk` stream held just the live tail.
This tool completes the migration:

- Identity is the ENVELOPE KEY (seq, from, ts, title, body hash), not the seq
  alone: distinct messages can share a filename seq (804 groups in fleet),
  and a seq-only set silently drops them.
- For each channel, scan the stream subject into a multiset of envelope keys.
- Publish every file whose key is missing, ascending, using the tailer's own
  parser (fleet_relay.build_relay_record) and envelope, with a per-file
  Nats-Msg-Id (squawk:<channel>:<seq>:<filename>).
- Idempotent: a re-run publishes nothing already in the stream.
- Read-only against the file store; never touches the tailer cursor.

Usage:
  squawk_nats_backfill.py [--dry-run] [--verify]
Channels come from SQUAWK_NATS_CHANNELS (same env as the tailer).
"""
import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import squawk_nats_tail as tail  # noqa: E402  (parser, envelope, token, constants)
import fleet_relay  # noqa: E402
import nats  # noqa: E402


def _key(env: dict) -> tuple:
    body = env.get("body") or ""
    return (
        env.get("seq", 0),
        env.get("from", ""),
        env.get("ts", ""),
        env.get("title", ""),
        hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def _file_key(channel: str, seq: int, path: Path):
    """Envelope key for a message file, via the tailer's parser. None on
    parse failure (mirrors the tailer: poison files are skipped)."""
    try:
        rec = fleet_relay.build_relay_record(
            path, channel=channel, identity=tail.AGENT,
            key_dir=tail.SQUAWK_ROOT / "keys")
    except Exception:
        return None
    env = tail._envelope(rec)
    env["seq"] = seq
    return _key(env), env


async def _existing_keys(js, channel: str) -> Counter:
    """Multiset of envelope keys already in the stream for <channel>.messages."""
    sub = await js.pull_subscribe(f"{channel}.messages", stream=tail.STREAM)
    found: Counter = Counter()
    while True:
        try:
            msgs = await sub.fetch(batch=500, timeout=2.0)
        except Exception:
            break
        if not msgs:
            break
        for m in msgs:
            try:
                env = json.loads(m.data.decode("utf-8"))
                found[_key(env)] += 1
            except Exception:
                pass
            await m.ack()
    try:
        await sub.unsubscribe()
    except Exception:
        pass
    return found


async def _run(dry_run: bool, verify_only: bool) -> int:
    token = tail._load_token()
    nc = await nats.connect(tail.NATS_URL, token=token)
    js = nc.jetstream()
    await tail._ensure_stream(js)

    rc = 0
    for channel in tail.CHANNELS:
        chan_dir = tail.SQUAWK_ROOT / channel
        files = tail._pending(chan_dir, -1) if chan_dir.is_dir() else []
        existing = await _existing_keys(js, channel)

        # walk files ascending; a file is missing when its key's remaining
        # count in the stream multiset is exhausted
        remaining = Counter(existing)
        missing = []
        unparsed = 0
        for seq, path in files:
            fk = _file_key(channel, seq, path)
            if fk is None:
                unparsed += 1
                continue
            key, env = fk
            if remaining[key] > 0:
                remaining[key] -= 1
            else:
                missing.append((seq, path, env))
        stream_only = sum(remaining.values())
        print(f"[{channel}] files={len(files)} in-stream={sum(existing.values())} "
              f"missing={len(missing)} stream-only={stream_only} unparsed={unparsed}",
              flush=True)
        if verify_only:
            if missing:
                rc = 1
            continue
        if dry_run:
            continue
        done = 0
        for seq, path, env in missing:
            data = json.dumps(env, ensure_ascii=False).encode("utf-8")
            headers = {"Nats-Msg-Id": f"squawk:{channel}:{seq}:{path.name}"}
            try:
                await js.publish(f"{channel}.messages", data, headers=headers)
            except Exception as e:
                print(f"[{channel}] publish failed {seq}: {e} -- stopping channel",
                      flush=True)
                rc = 1
                break
            done += 1
            if done % 500 == 0:
                print(f"[{channel}] published {done}/{len(missing)}", flush=True)
        print(f"[{channel}] published {done} messages", flush=True)

    await nc.close()
    return rc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_run(args.dry_run, args.verify)))


if __name__ == "__main__":
    main()
