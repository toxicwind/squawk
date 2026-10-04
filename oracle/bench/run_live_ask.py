#!/usr/bin/env python3
"""Live proving run: one ask through the herd, end to end.

This is the script the durability proof uses: after a supervision restart,
re-run it and confirm a fresh verdict. Writes a timestamped report to
work/proof-runs/ and prints the verdict JSON.

Usage: python3 bench/run_live_ask.py "Will <X> happen by <date>?" [--timeout 90]
"""
import json
import os
import sys
import time

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
sys.path.insert(0, BIN)

import oracle_ask  # noqa: E402  (after sys.path.insert for sibling-dir import)


def main(argv):
    if len(argv) < 2 or argv[1].startswith("--"):
        print(__doc__)
        return 2
    question = argv[1]
    timeout = 90.0
    for i, a in enumerate(argv[2:]):
        if a == "--timeout" and i + 3 <= len(argv):
            timeout = float(argv[i + 3])
    t0 = time.time()
    verdict = oracle_ask.run_ask(question, timeout_s=timeout)
    elapsed = time.time() - t0
    work = os.environ.get("ORACLE_WORK",
                          "/home/toxic/estate/ranch/squawk/oracle/work")
    outdir = os.path.join(work, "proof-runs")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "proof-%d.json" % int(t0))
    with open(path, "w") as f:
        json.dump({"ts": t0, "elapsed_s": round(elapsed, 2),
                   "verdict": verdict}, f, indent=2, default=str)
    print(json.dumps(verdict, indent=2, default=str))
    print("PROOF report: %s status=%s tier=%s p=%.3f elapsed=%.1fs" %
          (path, verdict.get("status"), verdict.get("tier"),
           verdict.get("probability") or 0, elapsed))
    return 0 if verdict.get("status") == "verdict" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
