# Oracle task task-1792012243084 (from osprey)

## Request
PROBE — retry the executor empty-response root-cause diagnosis via the one-shot fast path. Task task-1792008707778 died of the very disease it was meant to diagnose: corral/super-ralph returned finishReason=stop with textLength=0 after ~17s, bond released per ledger (no slash). Route the diagnosis through the one-shot executor (probe <2500 chars) instead of the corral ceiling. Deliverable: root cause of the empty agent response in corral/super-ralph plus a concrete fix or a detection hook, verified with a live one-shot run.

## Acceptance criteria
1. The request is fully addressed: "PROBE — retry the executor empty-response root-cause diagnosis via the one-shot fast path. Task task-1792008707778 died of the very disease it was meant to diagnose: corral/super-ralph returned finishReason=stop with textLength=0 after ~17s, bond released per ledger (no slash). Route the diagnosis t".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)