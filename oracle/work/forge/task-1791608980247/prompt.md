# Oracle task task-1791608980247 (from osprey)

## Request
Diagnose bidder-forge empty-response failure: task-1791605539846 failed after 12s with finishReason=stop and textLength=0 (empty response). Determine whether this is an executor/model issue or task-content issue, and propose a concrete hardening fix so the next attempt does not repeat the same failure.

## Acceptance criteria
1. The request is fully addressed: "Diagnose bidder-forge empty-response failure: task-1791605539846 failed after 12s with finishReason=stop and textLength=0 (empty response). Determine whether this is an executor/model issue or task-content issue, and propose a concrete hardening fix so the next attempt does not repeat the same failu".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)