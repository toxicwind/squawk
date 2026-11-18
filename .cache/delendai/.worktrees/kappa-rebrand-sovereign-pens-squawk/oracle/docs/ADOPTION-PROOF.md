# Oracle Intake — Adoption Proof (2026-09-20)

The oracle is the fleet front door. This document proves the intake path is
**live and complete** — verified end-to-end by lane-oracle-connector
(2026-09-20 ~21:49–21:50 MDT), not asserted from code reading.

## The wiring (observed, not inferred)

- Intake source: `agents/oracle-market/bin/oracle_intake.py` — six routes:
  `TASK`, `DEBATE`, `RESEARCH`, `PETITION`, `DIRECT`, `REJECT`.
- `oracle_loop.py` consumes `intake_request` (~line 1090); `handle_intake()`
  calls `triage()`.
- `TASK` creates a control-signed `task_post`; `DEBATE` opens a real debate;
  other routes are ledgered and announced.
- `pitchfork.toml` sets `ORACLE_INTAKE="1"`; the running oracle-market
  process (PID 102107) had `ORACLE_INTAKE=1` in `/proc/102107/environ`
  (rules out the pitchfork stale-snapshot issue).

## Unit test

```
cd agents/oracle-market && python3 bin/test_oracle_intake.py
INTAKE_UNIT_OK routes=('TASK', 'DEBATE', 'RESEARCH', 'PETITION', 'DIRECT', 'REJECT')
hints=['code-fix', 'docs', 'probe', 'research']
```

## Live end-to-end: TASK

Posted via `bin/post_intake.py` from lane-oracle-connector:

> probe the yote-connector /health route on 127.0.0.1:18301 and report the transport

Channel file: `100193-lane-oracle-connector-intake-1789962586.md`.
Ledger sequence: `intake-decision` (route TASK) → `task_open`
(`intake-1789962586468`) → two `bid_accepted` → `assigned` →
`stake_released` → `settled`. Final proof: `success=true`, winner
`bidder-scout`.

## Live: REJECT

Empty request produced `intake-decision REJECT empty request` and fleet
note `intake: REJECTED (empty request):` — the garbage filter works.

## Live: DIRECT

`!urgent adoption-verification ping from lane-oracle-connector (test only)`
produced `intake-decision DIRECT urgent flag`, `intake_direct`, and a fleet
note — the urgent path works.

## Verdict

Adoption is real: unit-tested, process-verified, and exercised live across
TASK, REJECT, and DIRECT routes with full ledger settlement. **No oracle
source changes were needed** — this lane added no intake code, only this
proof. Reported in fleet seq 11765.
