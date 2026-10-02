#!/usr/bin/env python3
"""Market watchdog for the oracle-market (2026-09-20).

Event-driven (inotify on the ledger dir, no polling): tails
agents/oracle-market/ledger/ledger.jsonl and counts consecutive no_assign
closes with reason no-valid-bids / no-eligible-bids. Any assigned/settled
row resets the counter. At 3 consecutive silent closes while both bidder
PIDs are alive (flock lock files), restarts the bidders via pitchfork,
posts a fleet note, logs a watchdog_restart row, and cools down 5 minutes.

Single instance per market (flock). Persistent agent: may file upgrade
petitions under market governance.
"""

import fcntl
import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
_spec = importlib.util.spec_from_file_location("oracle_loop", BIN / "oracle_loop.py")
ol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ol)

LEDGER = ol.LEDGER
FLEET = ol.FLEET
FROM = "market-watchdog"
SILENT_REASONS = {"no-valid-bids", "no-eligible-bids"}
TRIGGER = 3
COOLDOWN_S = 300
PITCHFORK_PATH = "/home/toxic/.local/share/mise/shims"


def log(event, **kw):
    kw.update({"event": event, "ts": time.time(), "from": FROM})
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(kw) + "\n")


class Watchdog:
    def __init__(self):
        self.running = True
        self.silent = 0
        self.offset = 0
        self._last_restart = 0.0
        self._last_note = 0.0
        self.fleet = ol.Poster(FLEET, "fleet")
        self._lock_fh = open(BIN / "market-watchdog.lock", "w")
        try:
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.stderr.write("market-watchdog: another instance running; exit\n")
            sys.exit(2)
        self._lock_fh.write(str(os.getpid()))
        self._lock_fh.flush()
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        # watch the ledger DIR (the file may be rotated/recreated)
        mask = ol.IN_CLOSE_WRITE | ol.IN_MOVED_TO | ol.IN_CREATE
        self._lfd = ol.inotify_init(LEDGER.parent, mask=mask)
        self._lf = None
        self._reopen_ledger()
        # start at end: only NEW rows count
        self._lf.seek(0, os.SEEK_END)
        self.offset = self._lf.tell()
        self._wake_r, self._wake_w = os.pipe()
        for pfd in (self._wake_r, self._wake_w):
            flags = fcntl.fcntl(pfd, fcntl.F_GETFL)
            fcntl.fcntl(pfd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _stop(self, *_):
        self.running = False
        try:
            os.write(self._wake_w, b"x")
        except (OSError, AttributeError):
            pass

    def _reopen_ledger(self):
        if self._lf is not None:
            try:
                self._lf.close()
            except OSError:
                pass
        self._lf = open(LEDGER, "a+", encoding="utf-8")
        st = os.stat(LEDGER)
        self._ledger_id = (st.st_dev, st.st_ino)

    def _check_ledger(self):
        try:
            st = os.stat(LEDGER)
        except OSError:
            return
        if (st.st_dev, st.st_ino) != self._ledger_id:
            self._reopen_ledger()
            self.offset = 0
        elif st.st_size < self.offset:
            self.offset = 0  # truncated/rotated
        self._lf.seek(self.offset)
        for line in self._lf:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            self._on_row(row)
        self.offset = self._lf.tell()

    def _on_row(self, row):
        ev = row.get("event")
        if ev == "no_assign" and row.get("reason") in SILENT_REASONS:
            self.silent += 1
            log("watchdog_silent", count=self.silent,
                task_id=row.get("task_id"), reason=row.get("reason"))
            if self.silent >= TRIGGER:
                self._maybe_restart()
        elif ev in ("assigned", "settled"):
            if self.silent:
                log("watchdog_reset", count=self.silent)
            self.silent = 0

    def _bidders_alive(self):
        for bid in ("forge", "scout"):
            try:
                pid = int((BIN / f"bidder-{bid}.lock").read_text().strip())
            except (OSError, ValueError):
                return False
            try:
                os.kill(pid, 0)
            except OSError:
                return False
        return True

    def _say(self, text, cooldown=60):
        now = time.time()
        if now - self._last_note < cooldown:
            return
        self._last_note = now
        try:
            self.fleet.post("note", f"watchdog-{int(now)}", text,
                            frm=FROM, raw_body=True)
        except OSError:
            pass

    def _maybe_restart(self):
        now = time.time()
        if now - self._last_restart < COOLDOWN_S:
            return
        if not self._bidders_alive():
            # genuinely dead: pitchfork's own retry owns that case
            log("watchdog_skip", reason="bidder-dead")
            self.silent = 0
            return
        self._last_restart = now
        self.silent = 0
        env = dict(os.environ)
        env["PATH"] = PITCHFORK_PATH + ":" + env.get("PATH", "")
        try:
            p = subprocess.run(
                ["pitchfork", "restart",
                 "sovereign/bidder-forge", "sovereign/bidder-scout"],
                capture_output=True, text=True, timeout=60, env=env)
            ok = p.returncode == 0
            detail = (p.stdout + p.stderr)[-500:]
        except Exception as e:  # noqa: BLE001
            ok = False
            detail = f"{type(e).__name__}: {e}"
        log("watchdog_restart", ok=ok, detail=detail)
        self._say(
            "market-watchdog: 3 auctions closed with no bids while both "
            f"bidders were alive - restarted the bidders "
            f"({'ok' if ok else 'FAILED'}). If this keeps happening, "
            "the market needs a human.",
            cooldown=0)

    def run(self):
        log("watchdog_start", pid=os.getpid())
        try:
            while self.running:
                # drain inotify (names are .md-filtered; we only care
                # that the ledger dir changed)
                ol.inotify_names(self._lfd)
                self._check_ledger()
                try:
                    while os.read(self._wake_r, 64):
                        pass
                except OSError:
                    pass
                # no timeout: pure push wakeups
                select.select([self._lfd, self._wake_r], [], [])
        finally:
            try:
                os.close(self._lfd)
            except OSError:
                pass
            os.close(self._wake_r)
            os.close(self._wake_w)
            log("watchdog_stop")


def main():
    Watchdog().run()


if __name__ == "__main__":
    main()
