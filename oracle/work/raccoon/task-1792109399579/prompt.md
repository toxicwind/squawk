# Oracle task task-1792109399579 (from osprey)

## Request
Empty-response disease persists POST-credential-fix: task-1792105788696 one-shot returned empty at 17:10 MDT, after the 16:54 credential fix and live-verified real tokens from flock :25193. Localize the fault in executor request shaping. Capture the exact HTTP request the one-shot executor sends to flock :25193 (full headers + body), replay the identical request raw via curl from yote, diff the two responses. Report: does the raw replay return tokens while the executor-shaped request returns empty, or do both return empty? If both empty, include the exact request body the executor produced and any flock-side error. Deliverable: both responses plus the shaping diff. No executor internals changes in this task.

## Acceptance criteria
1. The request is fully addressed: "Empty-response disease persists POST-credential-fix: task-1792105788696 one-shot returned empty at 17:10 MDT, after the 16:54 credential fix and live-verified real tokens from flock :25193. Localize the fault in executor request shaping. Capture the exact HTTP request the one-shot executor sends to ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)