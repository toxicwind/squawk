# Oracle task task-1792368579635 (from osprey)

## Request
Diagnose the recurring model-guard health=ERR:URLError flap: it has cleared and re-errored several times tonight (fleet log 2026-10-18 ~22:46-00:03 UTC). Determine whether the health probe URL drifted vs daemon restart churn; report root cause with evidence and a durable fix. Do not touch the live :25193 flock service.

## Acceptance criteria
1. The request is fully addressed: "Diagnose the recurring model-guard health=ERR:URLError flap: it has cleared and re-errored several times tonight (fleet log 2026-10-18 ~22:46-00:03 UTC). Determine whether the health probe URL drifted vs daemon restart churn; report root cause with evidence and a durable fix. Do not touch the live :".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)