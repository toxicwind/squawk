#!/usr/bin/env python3
"""Local driver: run the refresh helper on awrawr-pc via bridge, script inline.

Usage: driver.py <step>  (step: seed | stale | append2 | lww | idem | clamp)
Prints the raw bridge JSON result. AWRAWR_TRANSPORT=https is forced.
Each invocation is one stateless bridge round trip.
"""
import json, os, subprocess, sys

EXEC = os.path.expanduser("~/workspace/skills/awrawr-mcp/bin/exec.py")
BASE = "/home/toxic/session-bus-refresh"
SRC = BASE + "/chat-scratch-082e5a1c.md"
ENV = dict(os.environ, AWRAWR_TRANSPORT="https")

with open(os.path.expanduser("~/workspace/session-bus-refresh/refresh_rejoin_cursor.py")) as f:
    SCRIPT = f.read()

SEED = [
    "[worker] joining session, rejoin requested",
    "[worker] catching up on thread",
    "DECISION: gamma",
]
APPEND2 = [
    "[worker] status: running checks",
    "DECISION: delta",
]
APPEND_EPSILON = ["DECISION: epsilon"]


def bridge(*argv, timeout=20):
    p = subprocess.run(
        [EXEC, "--json", "--timeout", str(timeout), "--argv"] + list(argv),
        capture_output=True, text=True, env=ENV, timeout=timeout + 60)
    return p.stdout.strip()


def sh(cmd, timeout=20):
    return bridge("bash", "-c", cmd, timeout=timeout)


def refresh(cursor, timeout=20):
    return bridge("python3", "-c", SCRIPT, SRC, str(cursor), timeout=timeout)


def step_seed():
    lines = " ".join('"%s"' % l.replace('"', '\\"') for l in SEED)
    return sh('mkdir -p %s && printf "%%s\\n" %s > %s && sha256sum %s && wc -l %s'
              % (BASE, lines, SRC, SRC, SRC))


def step_append2():
    lines = " ".join('"%s"' % l.replace('"', '\\"') for l in APPEND2)
    return sh('printf "%%s\\n" %s >> %s && sha256sum %s && wc -l %s'
              % (lines, SRC, SRC, SRC))


def step_lww():
    return sh('printf "%%s\\n" "DECISION: epsilon" >> %s && sha256sum %s && wc -l %s'
              % (SRC, SRC, SRC))


def step_hash():
    return sh('sha256sum %s && wc -l %s' % (SRC, SRC))


STEPS = {
    "seed": step_seed,
    "append2": step_append2,
    "lww": step_lww,
    "hash": step_hash,
}

if __name__ == "__main__":
    step = sys.argv[1]
    if step.startswith("refresh:"):
        print(refresh(step.split(":", 1)[1]))
    else:
        print(STEPS[step]())
