#!/usr/bin/env python3
"""Deterministic tests for the oracle-repair lifecycle (2026-09-21).

Covers: all six intake routes, signed research auctions, petition debates
with evidence + verdict, signed direct assignments, acceptance validation,
settlement-driven next-work (idle/busy/idempotent), and Super Ralph
command construction in the bidder.
"""
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

TMP = Path(tempfile.mkdtemp(prefix="oracle-repair-test-"))
os.environ["ORACLE_CHANNEL"] = str(TMP / "bid-market")
os.environ["ORACLE_FLEET"] = str(TMP / "fleet")
os.environ["ORACLE_WORK"] = str(TMP / "work")
os.environ["ORACLE_LEDGER"] = str(TMP / "ledger" / "ledger.jsonl")
os.environ["ORACLE_LOCK"] = str(TMP / "oracle.lock")
os.environ["ORACLE_REGISTRY_DIR"] = str(TMP / "registry")
for _d in ("bid-market", "fleet", "work", "ledger"):
    (TMP / _d).mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))

import mechanism as mech  # noqa: E402
import oracle_loop as ol  # noqa: E402

mech.save_profiles({
    "forge": {"key_id": "k-forge", "bidder_id": "bidder-forge",
              "secret": "s-forge", "capabilities": ["general"],
              "max_class": "standard", "stake": 100.0, "locked": {}},
    "scout": {"key_id": "k-scout", "bidder_id": "bidder-scout",
              "secret": "s-scout", "capabilities": ["general"],
              "max_class": "standard", "stake": 100.0, "locked": {}},
})

LOOP = ol.OracleLoop()
CHAN = Path(os.environ["ORACLE_CHANNEL"])
N = 0


def check(name, cond, detail=""):
    global N
    N += 1
    print(("PASS %s" % name) if cond else ("FAIL %s %s" % (name, detail)))
    if not cond:
        raise SystemExit("test failed: %s %s" % (name, detail))


def channel_msgs(msg_type=None):
    out = []
    for f in sorted(os.listdir(CHAN)):
        p = ol.parse_msg(CHAN / f)
        if not p:
            continue
        meta, data = p
        if msg_type and meta.get("msg_type") != msg_type:
            continue
        out.append((meta, data))
    return out


def ledger_events(event=None):
    out = []
    lp = Path(os.environ["ORACLE_LEDGER"])
    if not lp.exists():
        return out
    for line in lp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        if event and ev.get("event") != event:
            continue
        out.append(ev)
    return out


def intake(text, frm="tester"):
    LOOP.handle_intake({"from": frm}, {"text": text})


# 1. acceptance-report parser -------------------------------------------
f, m, items = ol._parse_acceptance_report(
    "work done\nACCEPTANCE-REPORT:\n- crit one: MET - evidence a\n"
    "- crit two: UNMET - ran out\n")
check("parser-found", f is True)
check("parser-not-all-met", m is False)
check("parser-items", len(items) == 2 and items[0][1] and not items[1][1])

f, m, items = ol._parse_acceptance_report(
    "ACCEPTANCE-REPORT:\n- a: MET - x\n- b: MET - y\n")
check("parser-all-met", f and m and len(items) == 2)

f, m, items = ol._parse_acceptance_report("nothing here")
check("parser-missing", not f and not m and items == [])

# 2. TASK intake -> signed Super Ralph task_post -------------------------
intake("build a small widget that prints hello")
posts = channel_msgs("task_post")
check("task-posted", len(posts) == 1, str(len(posts)))
meta, data = posts[0]
check("task-exec-mode", data.get("exec_mode") == "super-ralph")
check("task-ctl-signed", bool(meta.get("ctl_sig")) and bool(meta.get("ctl_ts")))
check("task-prompt", "ACCEPTANCE-REPORT:" in data.get("payload", ""))
check("task-no-print-stub", "print('intake-executed" not in data.get("payload", ""))
check("task-class", data.get("task_class") == "standard")
TID_TASK = data["task_id"]

# 3. RESEARCH intake -> signed biddable research task --------------------
intake("research current nim proxy routing options")
posts = channel_msgs("task_post")
check("research-posted", len(posts) == 2, str(len(posts)))
meta, data = posts[1]
check("research-tag", "research" in data.get("tags", []))
check("research-class", data.get("task_class") == "research")
check("research-exec-mode", data.get("exec_mode") == "super-ralph")
check("research-ctl", bool(meta.get("ctl_sig")))

# 4. DIRECT intake -> immediate signed assignment ------------------------
intake("!urgent restart the stuck worker now", frm="ember")
assigns = channel_msgs("assign")
check("direct-assign-published", len(assigns) == 1, str(len(assigns)))
meta, data = assigns[0]
TID_DIRECT = data["task_id"]
check("direct-winner", data.get("winner") == "bidder-forge", str(data.get("winner")))
check("direct-reveal", (data.get("reveal") or {}).get("mode") == "direct")
a = LOOP.auctions.get(TID_DIRECT)
check("direct-auction-assigned", a is not None and a.state == "ASSIGNED")
check("direct-bond-locked",
      TID_DIRECT in (LOOP.profiles["forge"].get("locked") or {}))
ev = [e for e in ledger_events("assigned") if e.get("task_id") == TID_DIRECT]
check("direct-ledger-row", len(ev) == 1 and ev[0].get("mode") == "direct")
dposts = [p for p in channel_msgs("task_post") if p[1].get("task_id") == TID_DIRECT]
check("direct-task-signed", len(dposts) == 1 and bool(dposts[0][0].get("ctl_sig")))

# 5. PETITION intake -> real debate with kind=petition --------------------
intake("petition to upgrade the market watchdog timer", frm="ember")
pd = [d for d in LOOP.debates.values() if d.kind == "petition"]
check("petition-debate-opened", len(pd) == 1, str(len(pd)))
DID = pd[0].debate_id

# 6. DEBATE intake -> normal debate ---------------------------------------
intake("should we switch the default model?", frm="ember")
nd = [d for d in LOOP.debates.values()
      if d.kind == "debate" and d.state == "OPEN"]
check("debate-opened", len(nd) == 1, str(len(nd)))

# 7. REJECT intake -> nothing --------------------------------------------
n_posts_before = len(channel_msgs("task_post"))
intake("", frm="ember")
check("reject-no-task", len(channel_msgs("task_post")) == n_posts_before)

# 8. petition evidence + verdict ------------------------------------------
d = LOOP.debates[DID]
LOOP.handle_debate_reply({"from": "forge", "task_id": DID},
                         {"text": "APPROVE: the watchdog needs a shorter "
                                  "leash; evidence: it missed 3 stalls."})
LOOP.handle_debate_reply({"from": "scout", "task_id": DID},
                         {"text": "APPROVE as well: stalls cost us money; "
                                  "ship it."})
check("petition-settled", d.state == "SETTLED")
sev = [e for e in ledger_events("debate_settled")
       if e.get("debate_id") == DID]
check("petition-verdict-approved",
      len(sev) == 1 and sev[0].get("verdict") == "approved",
      str(sev[0].get("verdict") if sev else None))
check("petition-evidence",
      len(sev[0].get("evidence", {})) == 2 if sev else False)
ptasks = [p for p in channel_msgs("task_post")
          if p[1].get("task_id", "").startswith("petition-")]
check("petition-task-opened", len(ptasks) == 1, str(len(ptasks)))

# 9. acceptance validation in handle_result -------------------------------
def good_output():
    return ("did the work\nACCEPTANCE-REPORT:\n"
            "- criterion 1: MET - done\n- criterion 2: MET - done\n")

def mk_assigned(tid, winner_short):
    body = LOOP._agentic_task_body(tid, "do the thing", "tester",
                                   ["probe"], "standard")
    a = LOOP.open_auction(body)
    mech.lock_bond(LOOP.profiles, winner_short, tid, mech.BOND)
    a.state = "ASSIGNED"
    a.winner = "bidder-" + winner_short
    a.price_paid = 0.0
    a.assign_ts = time.time()
    return a

def result_data(tid, winner, output):
    return {"task_id": tid, "bidder_id": winner, "success": True,
            "output": output,
            "result_hash": hashlib.sha256(output.encode()).hexdigest(),
            "artifacts": [], "duration_ms": 1000, "error": "",
            "posted_ts": time.time()}

# 9a. good agentic result verifies
T1 = "t-settle-1"
mk_assigned(T1, "forge")
dec = LOOP.handle_result({"from": "bidder-forge"},
                         result_data(T1, "bidder-forge", good_output()),
                         verify_sig=False)
check("result-verified", dec is not None and dec["verified"] is True,
      str(dec))

# 9b. missing ACCEPTANCE-REPORT -> not verified
T2 = "t-settle-2"
mk_assigned(T2, "scout")
dec = LOOP.handle_result({"from": "bidder-scout"},
                         result_data(T2, "bidder-scout", "did stuff, no report"),
                         verify_sig=False)
check("result-unverified-no-report",
      dec is not None and dec["verified"] is False
      and "acceptance-report-missing" in dec["notes"], str(dec))

# 9c. empty output -> not verified even with success=true
T3 = "t-settle-3"
mk_assigned(T3, "forge")
dec = LOOP.handle_result({"from": "bidder-forge"},
                         result_data(T3, "bidder-forge", "   "),
                         verify_sig=False)
check("result-unverified-empty",
      dec is not None and dec["verified"] is False
      and "empty-output" in dec["notes"], str(dec))

# 10. settlement -> autonomous next-work ----------------------------------
def next_works(prev=None):
    ms = channel_msgs("next_work")
    return [m for m in ms if prev is None or m[1].get("prev_task") == prev]

# T1 settled while T2/T3 were OPEN/ASSIGNED at the time... settle T2,T3 now
# and check: next_work fires only when nothing is in flight.
LOOP.handle_result({"from": "bidder-scout"},
                   result_data(T2, "bidder-scout", good_output()),
                   verify_sig=False)
LOOP.handle_result({"from": "bidder-forge"},
                   result_data(T3, "bidder-forge", good_output()),
                   verify_sig=False)
# T1..T3 all settled; DIRECT task still ASSIGNED -> busy, no next_work yet
check("nextwork-suppressed-while-busy", next_works() == [],
      str(len(next_works())))
# settle the DIRECT task with a good result
a = LOOP.auctions[TID_DIRECT]
out = good_output()
dec = LOOP.handle_result({"from": a.winner}, result_data(
    TID_DIRECT, a.winner, out), verify_sig=False)
check("direct-settled", dec is not None and dec["verified"] is True,
      str(dec))
nw = next_works(TID_DIRECT)
check("nextwork-fired-when-idle", len(nw) == 1, str(len(nw)))
# idempotent: second trigger for the same settlement changes nothing
LOOP._maybe_start_next_work(TID_DIRECT)
check("nextwork-idempotent", len(next_works(TID_DIRECT)) == 1)

# 11. bidder Super Ralph command construction ------------------------------
import bidder  # noqa: E402

stub = TMP / "super-ralph-stub"
stub.write_text("#!/bin/sh\n"
                'echo "model=$NIM_MODEL bypass=$NIM_PROXY_BYPASS base=$NIM_BASE_URL"\n'
                'echo "args: $@"\n'
                'echo "FINAL-REPLY-OK"\n')
stub.chmod(0o755)
old_bin = bidder.RALPH_BIN
bidder.RALPH_BIN = stub
try:
    ns = SimpleNamespace(name="testbot", say=lambda *a, **k: None)
    wd = TMP / "w" / "t1"
    wd.mkdir(parents=True, exist_ok=True)
    ok, out, err, dur = bidder.Bidder._run_super_ralph(
        ns, {"task_id": "t1", "payload": "do things"}, wd, {}, 60000,
        time.time())
    check("ralph-ok", ok is True, err[:200])
    check("ralph-model-env", "model=kimi-k3-nim" in out, out[:200])
    check("ralph-bypass-env", "bypass=1" in out, out[:200])
    check("ralph-base-env", "base=http://127.0.0.1:25100/v1" in out, out[:200])
    check("ralph-skip-questions", "--skip-questions" in out, out[:300])
    check("ralph-final-reply", "FINAL-REPLY-OK" in out)
    check("ralph-prompt-file", (wd / "prompt.md").read_text() == "do things")
    inv = wd / "ralph-invocation.txt"
    check("ralph-invocation-evidence",
          inv.exists() and "kimi-k3-nim" in inv.read_text())
finally:
    bidder.RALPH_BIN = old_bin

# missing binary -> explicit failure, not a confusing python traceback
bidder.RALPH_BIN = Path("/nonexistent/super-ralph")
try:
    ns = SimpleNamespace(name="testbot", say=lambda *a, **k: None)
    wd2 = TMP / "w" / "t2"
    wd2.mkdir(parents=True, exist_ok=True)
    ok, out, err, dur = bidder.Bidder._run_super_ralph(
        ns, {"task_id": "t2", "payload": "x"}, wd2, {}, 60000, time.time())
    check("ralph-missing-bin", ok is False and "not found" in err, err[:200])
finally:
    bidder.RALPH_BIN = old_bin

# 12. F2: parser tolerates literal \n escapes ------------------------------
esc = ("poem line one\\npoem line two\\n\\nACCEPTANCE-REPORT:\\n"
       "- crit one: MET - evidence\\n- crit two: MET - evidence\\n")
f, m, items = ol._parse_acceptance_report(esc)
check("parser-escaped-found", f is True)
check("parser-escaped-met", m is True and len(items) == 2)

# 13. F2a: bidder canonicalizes Ralph stdout escapes -----------------------
stub_esc = TMP / "super-ralph-stub-esc"
stub_esc.write_text("#!/bin/sh\nprintf 'l1\\\\nl2\\\\nACCEPTANCE-REPORT:\\\\n- a: MET - x\\\\n'\n")
stub_esc.chmod(0o755)
bidder.RALPH_BIN = stub_esc
try:
    ns = SimpleNamespace(name="testbot", say=lambda *a, **k: None)
    wd3 = TMP / "w" / "t3"
    wd3.mkdir(parents=True, exist_ok=True)
    ok, out, err, dur = bidder.Bidder._run_super_ralph(
        ns, {"task_id": "t3", "payload": "x"}, wd3, {}, 60000, time.time())
    check("ralph-unescape", ok is True and "\n" in out and "\\n" not in out,
          repr(out[:80]))
finally:
    bidder.RALPH_BIN = old_bin

# 14. F1: artifact filtering drops dotfiles/dotdirs and non-files ---------
wd4 = TMP / "w" / "t4"
wd4.mkdir(parents=True, exist_ok=True)
(wd4 / "prompt.md").write_text("p")
(wd4 / "result.txt").write_text("r")
(wd4 / ".super-ralph").mkdir()
(wd4 / ".smithers").mkdir()
(wd4 / "subdir").mkdir()
arts = bidder.Bidder._collect_artifacts(wd4, set())
check("artifacts-filtered", arts == ["prompt.md", "result.txt"],
      str(arts))
arts2 = bidder.Bidder._collect_artifacts(wd4, {"prompt.md"})
check("artifacts-before-excluded", arts2 == ["result.txt"], str(arts2))

print("ALL %d CHECKS PASSED" % N)
