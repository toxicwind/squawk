#!/usr/bin/env python3
"""oracle-core daemon: HTTP front door for the fused Oracle.

Supervised by pitchfork as sovereign/oracle-core (see pitchfork.toml).
Endpoints (localhost only):
  GET  /health  -> {"ok": true, "uptime_s": ..., "verdicts": n}
  POST /ask     -> {"question": str, "models"?: [...], "timeout_s"?: float,
                    "evidence"?: [...], "allow_debate"?: bool}
                   -> verdict JSON (same shape as the oracle-ask CLI)

Durability: stateless across restarts except the verdict ledger and
calibration state on disk (work/). A restart loses nothing but in-flight
asks. Never touches the control key, squawk, or credentials.
"""
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BIN)

import oracle_ask  # noqa: E402  (after sys.path.insert for sibling-dir import)

LISTEN = os.environ.get("ORACLE_CORE_LISTEN", "127.0.0.1:25151")
LOG = os.path.join(os.environ.get("ORACLE_WORK",
                                  "/home/toxic/estate/ranch/squawk/oracle/work"),
                   "oracle-core.log")
START = time.time()
VERDICTS = 0


def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "oracle-core/1.0"

    def _send(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "uptime_s": time.time() - START,
                             "verdicts": VERDICTS})
        else:
            self._send(404, {"ok": False, "error": "unknown path"})

    def do_POST(self):
        global VERDICTS
        if self.path != "/ask":
            self._send(404, {"ok": False, "error": "unknown path"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._send(400, {"ok": False, "error": "bad JSON: %s" % e})
            return
        question = (req.get("question") or "").strip()
        if not question:
            self._send(400, {"ok": False, "error": "question required"})
            return
        t0 = time.time()
        try:
            verdict = oracle_ask.run_ask(
                question,
                models=req.get("models"),
                timeout_s=float(req.get("timeout_s", 90)),
                evidence_items=req.get("evidence"),
                allow_debate=bool(req.get("allow_debate", True)),
                budget_s=float(req.get("budget_s", 240)))
            VERDICTS += 1
            log("ask ok tier=%s p=%.3f latency=%.1fs q=%.60s" %
                (verdict.get("tier"), verdict.get("probability") or 0,
                 time.time() - t0, question))
            self._send(200, verdict)
        except Exception as e:
            log("ask ERROR %s\n%s" % (e, traceback.format_exc(limit=5)))
            self._send(500, {"ok": False, "error": "%s: %s"
                             % (type(e).__name__, e)})

    def log_message(self, fmt, *args):  # quiet default logging
        log("http " + fmt % args)


def main():
    host, port = LISTEN.rsplit(":", 1)
    srv = ThreadingHTTPServer((host, int(port)), Handler)
    log("oracle-core listening on %s (pid %d)" % (LISTEN, os.getpid()))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
