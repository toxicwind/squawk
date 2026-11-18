#!/usr/bin/env python3
"""Stub-based functional tests for the debate-tier P3 deadline + liveness
hardening (Nightjar cycle-8).

STUBS ONLY: chat_fn is always a local stub. Never touches the herd, never
burns judge budget.

Proves:
  1. A debate cannot exceed its absolute deadline (per-round pre-check AND
     mid-round abandon of a wedged chat_fn); "deadline-capped" is reported.
  2. Advocates that never return a live result are EXCLUDED from
     advocate_finals — no phantom seeded-prior votes.
  3. Unparseable advocate output fails the round (no prior+0.02 drift).

Run:  python3 bin/test_debate_deadline.py
Exit 0 = all pass, 1 = failures.
"""
import os
import sys
import time

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BIN)

import escalation

FAILURES = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name
          + (" (%s)" % detail if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def _live_stub(responses):
    """chat_fn stub: dict model -> str content | Exception instance."""
    def fn(model, prompt, timeout_s):
        r = responses.get(model, "0.5")
        if isinstance(r, BaseException):
            raise r
        return {"content": r}
    return fn


# ---------------------------------------------------------------- 1a: per-round pre-check
def test_deadline_precheck_skips_doomed_rounds():
    calls = []

    def fn(model, prompt, timeout_s):
        calls.append(model)
        return {"content": "0.6"}

    t0 = time.time()
    d = escalation.debate_tier("Q?", "C", "ev", ["a", "b"],
                               chat_fn=fn, k=2, max_rounds=3,
                               per_advocate_timeout_s=30.0,
                               deadline=t0 + 3.0)  # < DEBATE_MIN_ROUND_S
    el = time.time() - t0
    check("deadline pre-check: no rounds issued", d["rounds"] == 0 and calls == [],
          "rounds=%r calls=%r" % (d["rounds"], calls))
    check("deadline pre-check: deadline_capped set", d["deadline_capped"] is True)
    check("deadline pre-check: fast return", el < 2.0, "elapsed=%.2fs" % el)
    check("deadline pre-check: no finals, all dead",
          d["advocate_finals"] == [] and d["dead_advocates"] == 4,
          repr(d["advocate_finals"]))


# ------------------------------------------------------- 1b: mid-round abandon
def test_deadline_abandons_wedged_round():
    def wedged(model, prompt, timeout_s):
        time.sleep(15)  # longer than the deadline; never returns in time
        return {"content": "0.6"}

    t0 = time.time()
    d = escalation.debate_tier("Q?", "C", "ev", ["a", "b"],
                               chat_fn=wedged, k=2, max_rounds=3,
                               per_advocate_timeout_s=30.0,
                               deadline=t0 + 7.0)
    el = time.time() - t0
    check("mid-round abandon: returns near deadline", el < 12.0,
          "elapsed=%.2fs" % el)
    check("mid-round abandon: deadline_capped set", d["deadline_capped"] is True)
    check("mid-round abandon: wedged advocates not live",
          d["advocate_finals"] == [] and d["dead_advocates"] == 4,
          "finals=%r dead=%r" % (d["advocate_finals"], d["dead_advocates"]))
    cats = {r["failure_category"] for r in d["failure_records"]}
    check("mid-round abandon: timeout failure records", cats == {"timeout"},
          repr(cats))


# ------------------------------------------------- 2: never-live advocates excluded
def test_never_live_advocates_do_not_vote():
    # d1/d2 always raise; ok1/ok2 answer. k=2: YES->{d1,ok1}, NO->{ok2,d2}.
    # d1 fails then retries on ok1 -> live. d2 fails then retries on d1
    # -> still dead. Exactly one phantom must be excluded.
    stub = _live_stub({
        "d1": RuntimeError("boom"), "d2": RuntimeError("boom"),
        "ok1": "0.72", "ok2": "0.31",
    })
    d = escalation.debate_tier("Q?", "C", "ev", ["d1", "ok1", "ok2", "d2"],
                               chat_fn=stub, k=2, max_rounds=2,
                               per_advocate_timeout_s=5.0,
                               deadline=time.time() + 60)
    check("liveness: exactly one dead advocate", d["dead_advocates"] == 1,
          "dead=%r" % d["dead_advocates"])
    check("liveness: 3 finals, not 4", len(d["advocate_finals"]) == 3,
          repr(d["advocate_finals"]))
    priors = {round(a["posterior"], 4) for a in d["advocate_finals"]}
    check("liveness: no phantom seeded priors in finals",
          not (0.85 in priors or 0.15 in priors), repr(priors))
    check("liveness: retry made d1 live via ok1",
          any(a["model"] == "ok1" and a["side"] == "YES"
              for a in d["advocate_finals"]),
          repr(d["advocate_finals"]))
    cats = {r["failure_category"] for r in d["failure_records"]}
    check("liveness: executor failure records emitted",
          "executor_error" in cats, repr(cats))


def test_all_dead_debate_returns_empty_finals():
    stub = _live_stub({"d1": RuntimeError("x"), "d2": ConnectionError("y")})
    d = escalation.debate_tier("Q?", "C", "ev", ["d1", "d2"],
                               chat_fn=stub, k=2, max_rounds=2,
                               per_advocate_timeout_s=5.0,
                               deadline=time.time() + 60)
    check("all-dead: finals empty", d["advocate_finals"] == [])
    check("all-dead: dead_advocates == 4", d["dead_advocates"] == 4)
    check("all-dead: reference posterior neutral", d["posterior"] == 0.5,
          repr(d["posterior"]))
    check("all-dead: failure records cover attempts",
          len(d["failure_records"]) >= 4, repr(len(d["failure_records"])))


# ------------------------------------------------- 3: unparseable output fails the round
def test_extract_number_no_drift():
    p, ok = escalation._extract_number("0.62", 0.5)
    check("extract: parses a number", ok and p == 0.62, repr((p, ok)))
    p, ok = escalation._extract_number("I cannot decide, both sides argue well", 0.5)
    check("extract: unparseable fails, no +0.02 drift",
          (not ok) and p == 0.5, repr((p, ok)))
    p, ok = escalation._extract_number("maybe 0,75?", 0.5)
    check("extract: comma decimal still parses", ok and p == 0.75, repr((p, ok)))


def test_unparseable_round_fails_and_excludes():
    stub = _live_stub({"u1": "no number here, just words",
                       "u2": "also wordy, no digits at all"})
    d = escalation.debate_tier("Q?", "C", "ev", ["u1", "u2"],
                               chat_fn=stub, k=1, max_rounds=1,
                               per_advocate_timeout_s=5.0,
                               deadline=time.time() + 60)
    check("unparseable: advocate excluded from finals",
          d["advocate_finals"] == [] and d["dead_advocates"] == 2,
          repr(d["advocate_finals"]))
    cats = [r["failure_category"] for r in d["failure_records"]]
    check("unparseable: parse_failure records emitted",
          cats and all(c == "parse_failure" for c in cats), repr(cats))
    # direct unit check of the round primitive
    p, m, ok, fail = escalation._advocate_round(stub, "u1", "prompt", 0.5, 5.0)
    check("unparseable: _advocate_round ok=False, prior kept",
          (not ok) and p == 0.5 and m == "u1", repr((p, m, ok)))
    check("unparseable: failure record classified parse_failure",
          fail and fail["failure_category"] == "parse_failure", repr(fail))


# ------------------------------------------------- 4: all-live behavior unchanged
def test_all_live_debate_unchanged():
    stub = _live_stub({"a": "0.70", "b": "0.69", "c": "0.71", "d": "0.70"})
    d = escalation.debate_tier("Q?", "C", "ev", ["a", "b", "c", "d"],
                               chat_fn=stub, k=2, max_rounds=3,
                               per_advocate_timeout_s=5.0,
                               deadline=time.time() + 60)
    check("all-live: 4 finals", len(d["advocate_finals"]) == 4)
    check("all-live: none dead", d["dead_advocates"] == 0)
    check("all-live: no failure records", d["failure_records"] == [],
          repr(d["failure_records"]))
    check("all-live: converged on tight spread", d["converged"] is True)
    check("all-live: not deadline capped", d["deadline_capped"] is False)
    check("all-live: legacy call without deadline still works",
          escalation.debate_tier("Q?", "C", "ev", ["a", "b"],
                                 chat_fn=stub, k=1,
                                 max_rounds=1)["dead_advocates"] == 0)


def main():
    for name in sorted([k for k in list(globals()) if k.startswith("test_")]):
        try:
            globals()[name]()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("FAIL %s raised %r" % (name, e))
            FAILURES.append(name)
    print("---")
    if FAILURES:
        print("%d FAILURES: %s" % (len(FAILURES), ", ".join(sorted(set(FAILURES)))))
        return 1
    print("all debate deadline/liveness tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
