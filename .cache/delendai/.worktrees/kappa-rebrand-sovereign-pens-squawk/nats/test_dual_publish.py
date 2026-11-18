#!/usr/bin/env python3
"""test_dual_publish.py -- E2E proofs for the NATS dual-publish lane (Taps).

Run on yote with the squawk-nats venv:
  /home/toxic/.local/share/squawk-nats/venv/bin/python test_dual_publish.py

Proves:
  T1  publish -> both sinks receive (file feed AND NATS envelope, same seq)
  T2  kill NATS -> the custom file feed keeps working; on restart the tailer
      catches up (cursor logic) and the missed message lands in JetStream
  T3  restart nats-server -> JetStream history replays (durable file storage)

T2/T3 shell out to `pitchfork` to stop/start the nats daemon -- they need the
pitchfork binary on PATH. T1 only needs nats-server + tailer running.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

VENV_PY = "/home/toxic/.local/share/squawk-nats/venv/bin/python"
NATS_URL = os.environ.get("SQUAWK_NATS_URL", "nats://127.0.0.1:4222")
TOKEN_FILE = os.environ.get("SQUAWK_FEED_TOKEN_FILE",
                             "/home/toxic/.fleet-bus/squawk-relay/feed-token")
SQUAWK_ROOT = Path("/home/toxic/.fleet-bus/squawk-root")
CHANNEL = "fleet"

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{PASS if ok else FAIL}] {name}" + (f" -- {detail}" if detail else ""),
          flush=True)


def token():
    return Path(TOKEN_FILE).read_text().strip()


SQUAWK_BIN = "/home/toxic/.fleet-bus/bin/squawk"  # yote-native chat.py wrapper

def squawk_send(text):
    """Publish via the yote-native CLI (post -> file sink). Returns CLI output."""
    out = subprocess.run(
        [SQUAWK_BIN, "post", CHANNEL, "--from", "taps",
         "--title", "taps-e2e", "--body", text],
        capture_output=True, text=True, timeout=60)
    return out.stdout.strip() + out.stderr.strip()


def nats_eval(py):
    """Run a snippet with the venv python (has nats-py). Returns stdout."""
    out = subprocess.run([VENV_PY, "-c", py], capture_output=True, text=True,
                         timeout=90)
    if out.returncode != 0:
        raise RuntimeError(f"nats_eval failed: {out.stderr[-2000:]}")
    return out.stdout.strip()


SUB_SNIPPET = """
import asyncio, json, sys
import nats
async def main():
    tok = open(%r).read().strip()
    nc = await nats.connect(%r, token=tok)
    js = nc.jetstream()
    sub = await js.subscribe("fleet.messages", durable="taps-e2e-" + sys.argv[1][-8:])
    # drain anything already there, then wait for the probe
    probe = sys.argv[1]
    deadline = __import__("time").time() + 20
    while __import__("time").time() < deadline:
        try:
            m = await sub.next_msg(timeout=2)
            env = json.loads(m.data.decode())
            await m.ack()
            if probe in (env.get("body") or ""):
                print(json.dumps({"seq": env["seq"], "from": env.get("from")}))
                await nc.close(); return
        except Exception:
            pass
    print("TIMEOUT")
    await nc.close()
asyncio.run(main())
""" % (TOKEN_FILE, NATS_URL)


async def _t1():
    probe = "nats-e2e-probe-" + uuid.uuid4().hex[:8]
    t0 = time.time()
    res = squawk_send(probe)
    if "posted #" not in res:
        check("T1 file sink: squawk post accepted", False, res[-200:])
        return
    # find the file seq
    seq = None
    for _ in range(30):
        cands = [p for p in (SQUAWK_ROOT / CHANNEL).glob("*.md")
                 if probe in p.read_text()]
        if cands:
            seq = int(cands[0].name.split("-")[0])
            break
        time.sleep(1)
    check("T1 file sink: message file present", seq is not None,
          f"seq={seq}" if seq else "not found in 30s")
    if seq is None:
        return
    # wait for the envelope on NATS (fresh durable per probe)
    out = subprocess.run([VENV_PY, "-c", SUB_SNIPPET, probe],
                         capture_output=True, text=True, timeout=60)
    line = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "TIMEOUT"
    if line == "TIMEOUT":
        check("T1 NATS sink: envelope received", False,
              f"no envelope in 20s (send took {time.time()-t0:.1f}s)")
        return
    env = json.loads(line)
    check("T1 NATS sink: envelope received", True,
          f"seq={env['seq']} from={env['from']}")
    check("T1 seq agreement file==NATS", env["seq"] == seq,
          f"file={seq} nats={env['seq']}")


def _t2():
    probe = "nats-kill-probe-" + uuid.uuid4().hex[:8]
    # stop nats (owned path; nats is not squawk so pitchfork-restart allows it)
    subprocess.run(["pitchfork", "stop", "nats"], capture_output=True,
                   text=True, timeout=60)
    time.sleep(2)
    down = subprocess.run(["ss", "-ltn"], capture_output=True, text=True)
    nats_down = ":4222" not in down.stdout
    check("T2 NATS stopped", nats_down, "port 4222 free" if nats_down else "still listening")
    # file feed must keep working with NATS down
    res = squawk_send(probe)
    ok_send = "posted #" in res
    check("T2 file feed works with NATS down", ok_send, res[-120:])
    seq = None
    for _ in range(15):
        cands = [p for p in (SQUAWK_ROOT / CHANNEL).glob("*.md")
                 if probe in p.read_text()]
        if cands:
            seq = int(cands[0].name.split("-")[0])
            break
        time.sleep(1)
    # tailer must still be alive (it never crashes on NATS loss)
    tail = subprocess.run(["pitchfork", "status", "nats-tail"], capture_output=True,
                          text=True, timeout=30).stdout
    check("T2 tailer survives NATS loss", "running" in tail.lower(),
          tail.strip().splitlines()[-1][:100] if tail.strip() else "no status")
    # restart nats, tailer must catch up the missed message
    subprocess.run(["pitchfork", "start", "nats"], capture_output=True,
                   text=True, timeout=60)
    got = None
    for _ in range(45):
        out = subprocess.run([VENV_PY, "-c", SUB_SNIPPET, probe],
                             capture_output=True, text=True, timeout=40)
        line = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "TIMEOUT"
        if line != "TIMEOUT":
            got = json.loads(line)
            break
        time.sleep(2)
    check("T2 catch-up: missed message lands in JetStream after restart",
          got is not None and got["seq"] == seq,
          f"got seq={got['seq'] if got else None} want {seq}")


def _t3():
    info_py = """
import asyncio, json
import nats
async def main():
    tok = open(%r).read().strip()
    nc = await nats.connect(%r, token=tok)
    js = nc.jetstream()
    si = await js.stream_info("squawk")
    print(json.dumps({"msgs": si.state.messages, "bytes": si.state.bytes}))
    await nc.close()
asyncio.run(main())
""" % (TOKEN_FILE, NATS_URL)
    before = json.loads(nats_eval(info_py))
    subprocess.run(["pitchfork", "restart", "nats"], capture_output=True,
                   text=True, timeout=90)
    time.sleep(3)
    after = json.loads(nats_eval(info_py))
    check("T3 history survives nats-server restart",
          after["msgs"] >= before["msgs"] and after["msgs"] > 0,
          f"msgs before={before['msgs']} after={after['msgs']}")


def main():
    import asyncio
    print("== T1: dual-sink publish ==", flush=True)
    asyncio.run(_t1())
    print("== T2: NATS kill -> feed survives, catch-up ==", flush=True)
    _t2()
    print("== T3: restart -> history replays ==", flush=True)
    _t3()
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results)-len(failed)}/{len(results)} passed", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
