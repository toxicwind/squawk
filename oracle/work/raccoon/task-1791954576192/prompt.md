# Oracle task task-1791954576192 (from osprey)

## Request
Diagnose and fix the empty-response failure in the corral->super-ralph executor chain seen on task-1791950976412: raccoon won the task, corral returned empty (TEST-001 retry fell back to super-ralph), then super-ralph also returned empty after 1695s (finishReason=stop, textLength=0) and the task settled FLAGGED. Identify which layer dropped the output (shim, model route to nvidia/nemotron-3-ultra-550b-a55b on the flock chain, or agent handoff) and land a fix that keeps non-empty output flowing through settle. Reproduce against the same route before settling.

## Acceptance criteria
1. The request is fully addressed: "Diagnose and fix the empty-response failure in the corral->super-ralph executor chain seen on task-1791950976412: raccoon won the task, corral returned empty (TEST-001 retry fell back to super-ralph), then super-ralph also returned empty after 1695s (finishReason=stop, textLength=0) and the task set".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)