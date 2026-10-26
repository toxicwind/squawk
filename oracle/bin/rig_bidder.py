#!/usr/bin/env python3
"""Rig turn driver for market bidder lanes (2026-10-19, osprey).

Single-pass, no bespoke daemon loop: rig's cron drives the cadence
(agent_turn), this script does one poll -> bid -> run cycle and exits.
The sealed-bid protocol, keys, and runners are REUSED from bidder.py --
Bidder is imported as a library (its __main__ guard keeps the import
side-effect free). The old inotify daemon loop in bidder.py is retired;
this is the thin adapter that remains.

Usage:
  rig_bidder.py --turn --id forge [--state-dir DIR] [--dry-run]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import bidder as bidder_mod  # noqa: E402  (safe: __main__ guard, no loop)

# Lane params mirror bidder-<id>.sh (2026-10-19). The rig cron only passes
# --id; everything else is pinned here so turns are deterministic.
LANES = {
    "finch": dict(name="Finch", emoji="\U0001F426",
                  tags="forensics,verify,research,probe",
                  tagline="I verify what others claim and dig till the evidence talks. Point me at the uncertain thing."),
    "forge": dict(name="Forge", emoji="\U0001F528", tags="code-fix,probe",
                  tagline="I fix broken things and poke them till they confess. Point me at what's busted."),
    "raccoon": dict(name="Raccoon", emoji="\U0001F99D",
                    tags="probe,research,code-fix,verify,docs",
                    tagline="Raccoon here \u2014 I wash every task before I serve it. Probes, research, fixes, verification."),
    "scout": dict(name="Scout", emoji="\U0001F52D", tags="probe,research,docs",
                  tagline="I go first, look around, and report back. If it's unknown territory, I'm already halfway there!"),
    "vesper": dict(name="Vesper", emoji="\U0001F987", tags="probe,verify",
                   tagline="Vesper here \u2014 evening shepherd. I watch the lanes and verify what matters."),
    "warden": dict(name="Warden", emoji="\U0001F6E1",
                   tags="verify,drift-probe,docs",
                   tagline="I verify, re-check, and prove it. Drift, docs, or test runs - point me at the claim."),
}

TURN_BUDGET_S = 540.0  # a cron turn must never run unbounded
STATE_KEEP_FILES = 500


def load_state(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turn", action="store_true", required=True)
    ap.add_argument("--id", required=True, choices=sorted(LANES))
    ap.add_argument("--state-dir", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    lane = LANES[args.id]
    state_dir = Path(args.state_dir) if args.state_dir else \
        Path(f"/home/toxic/.openfang/workspaces/market-bidder-{args.id}")
    state_path = state_dir / "turn-state.json"
    state = load_state(state_path)

    t0 = time.time()
    summary = {"bids": 0, "executed": 0, "errors": []}

    # Reuse the Bidder as a library: keys, sealed bids, runners, result
    # signing all come from bidder.py. No daemon loop is started.
    bargs = argparse.Namespace(id=args.id, name=lane["name"],
                               emoji=lane["emoji"], tags=lane["tags"],
                               tagline=lane["tagline"])
    try:
        b = bidder_mod.Bidder(bargs)
    except SystemExit as e:
        # _acquire_lock exit(2): a pitchfork daemon still holds this lane.
        print("TURN_ABORT: lock held (pitchfork daemon still alive?)", flush=True)
        return 2
    # Restore durable turn state (the daemon kept this in memory).
    b.executed.update(state.get("executed", []))
    b.my_bids.update(state.get("my_bids", {}))
    seen_files = set(state.get("seen_files", []))

    ol, CHANNEL = bidder_mod.ol, bidder_mod.CHANNEL
    try:
        files = sorted(f for f in os.listdir(CHANNEL)
                       if bidder_mod.SEQ_RE.match(f))
    except OSError as e:
        print("TURN_ABORT: channel unreadable: %s" % e, flush=True)
        return 1
    # First run: the channel holds history (thousands of files). A poller
    # must not reprocess history -- mark everything seen, only NEW files
    # (posted after this agent starts) get processed.
    if not seen_files and not state.get("initialized"):
        seen_files.update(files)
        state["initialized"] = True
        save_state(state_path, state)
        print("TURN_DONE: initialized, %d historic files marked seen" % len(files),
              flush=True)
        return 0
    new_files = [f for f in files if f not in seen_files]

    for name in new_files:
        if time.time() - t0 > TURN_BUDGET_S:
            summary["errors"].append("turn budget exceeded; %d files deferred"
                                    % (len(new_files) - new_files.index(name)))
            break
        parsed = ol.parse_msg(CHANNEL / name)
        seen_files.add(name)
        if not parsed:
            continue
        meta, data = parsed
        if meta.get("from") == b.frm:
            continue
        mt = meta.get("msg_type", "")
        try:
            if mt == "task_post":
                if args.dry_run:
                    summary["bids"] += 0
                    continue
                before = len(b.my_bids)
                b.on_task_post(data)
                if len(b.my_bids) > before:
                    summary["bids"] += 1
            elif mt == "assign":
                # Synchronous single-pass execution (the daemon threaded
                # this; a turn driver joins its own work).
                tid = data.get("task_id")
                winner = data.get("winner")
                task = b._fetch_task(tid)
                if winner == b.frm and task is not None \
                        and tid not in b.executed:
                    b.say(b._pick("win", t=tid,
                                  c=b.my_bids.get(tid, 0)))
                    if not args.dry_run:
                        b.execute_task(task)
                        summary["executed"] += 1
                elif tid in b.my_bids and winner:
                    b.say(b._pick("lost", t=tid,
                                  w=winner.replace("bidder-", "")))
        except Exception as e:  # noqa: BLE001 -- one bad file never kills a turn
            summary["errors"].append("%s: %s" % (name, str(e)[:120]))

    state["seen_files"] = sorted(seen_files)[-STATE_KEEP_FILES:]
    state["my_bids"] = dict(b.my_bids)
    state["executed"] = sorted(b.executed)
    state["last_turn"] = time.time()
    save_state(state_path, state)
    print("TURN_DONE id=%s new_files=%d bids=%d executed=%d errors=%d "
          "dur_s=%.1f can_bid=%s" % (
              args.id, len(new_files), summary["bids"], summary["executed"],
              len(summary["errors"]), time.time() - t0, b.can_bid),
          flush=True)
    for e in summary["errors"][:5]:
        print("TURN_ERROR: %s" % e, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
