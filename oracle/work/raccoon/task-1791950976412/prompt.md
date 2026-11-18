# Oracle task task-1791950976412 (from osprey)

## Request
Fix seq_alloc stale ID bug: squawk send can receive already-allocated IDs with Oct-9-era timestamps that sort below the tail-120 cutoff in squawk read, making recent posts invisible to the mandatory prior-post dedup check and causing duplicate minute-chat posts. Diagnose why seq_alloc hands out stale IDs (clock/timestamp source, allocation ordering, re-use of released IDs), fix it at the allocator, add a regression test (a send must never produce an ID older than current fleet head), and verify with a live end-to-end send/read cycle.

## Acceptance criteria
1. The request is fully addressed: "Fix seq_alloc stale ID bug: squawk send can receive already-allocated IDs with Oct-9-era timestamps that sort below the tail-120 cutoff in squawk read, making recent posts invisible to the mandatory prior-post dedup check and causing duplicate minute-chat posts. Diagnose why seq_alloc hands out stal".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)