#!/usr/bin/env python3
"""oracle build entry

Canonical core suite (bench/test_core.py docstring: "Run: python3
bench/test_core.py"): deterministic unit tests for the Oracle core —
no model calls, no network, stdlib-only. Ends with
`sys.exit(1 if FAIL else 0)`.

Usage: scripts/flicker-build.py
Env:   FLICKER_URL (default http://127.0.0.1:25148)
Exit:  0 iff the flicker job succeeds (or an identical job already succeeded:
       CACHED). 1 on failure/timeout.
Job submission retries transient flicker 5xx/connection errors with
backoff; polling tolerates transient flicker errors until the timeout.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

NAME = "oracle-build"
BUILD_CMD = "python3 bench/test_core.py"
WORKDIR_REL = "."
TIMEOUT_S = 600
POLL_S = 2
SUBMIT_ATTEMPTS = 5
FLICKER_URL = os.environ.get("FLICKER_URL", "http://127.0.0.1:25148")


class FlickerError(Exception):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(FLICKER_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode()
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        raise FlickerError(
            "flicker %s %s -> HTTP %s: %s" % (method, path, e.code, text[:500]),
            retryable=500 <= e.code < 600)
    except OSError as e:
        raise FlickerError("flicker %s %s unreachable: %s" % (method, path, e),
                           retryable=True)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text  # raw log text


def submit(name, command):
    delay = 2
    for attempt in range(1, SUBMIT_ATTEMPTS + 1):
        try:
            return api("POST", "/api/jobs", {"name": name, "command": command})
        except FlickerError as e:
            if not e.retryable or attempt == SUBMIT_ATTEMPTS:
                raise SystemExit("submit failed: %s" % e)
            print("submit attempt %d failed (%s); retrying in %ds"
                  % (attempt, e, delay))
            time.sleep(delay)
            delay *= 2


def main():
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    workdir = os.path.normpath(os.path.join(repo, WORKDIR_REL))
    command = 'cd "%s" && %s' % (workdir, BUILD_CMD)

    sub = submit(NAME, command) or {}
    jid = sub.get("id")
    if jid is None:
        print("submit failed: no id in %r" % (sub,), file=sys.stderr)
        return 1
    print("submitted job id=%s" % jid)
    if sub.get("cached"):
        print("CACHED (id %s)" % jid)
        logs = api("GET", "/api/jobs/%s/logs" % jid) or ""
        tail = logs.splitlines()[-10:]
        if tail:
            print("\n".join(tail))
        return 0

    seen = 0
    deadline = time.time() + TIMEOUT_S
    while True:
        try:
            st = api("GET", "/api/jobs/%s" % jid) or {}
            status = st.get("status", "")
            logs = api("GET", "/api/jobs/%s/logs" % jid) or ""
        except FlickerError as e:
            print("(transient flicker error: %s; continuing)" % e)
            status, logs = "", ""
        if len(logs) < seen:
            seen = 0
        if len(logs) > seen:
            sys.stdout.write(logs[seen:])
            sys.stdout.flush()
            seen = len(logs)
        if status == "success":
            print("\nSUCCEEDED (id %s)" % jid)
            return 0
        if status == "failure":
            print("\nFAILED (id %s)" % jid, file=sys.stderr)
            return 1
        if time.time() >= deadline:
            print("\ntimeout waiting for job %s (last status %r)"
                  % (jid, status), file=sys.stderr)
            return 1
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
