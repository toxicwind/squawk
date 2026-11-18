# Oracle task task-1792015828203 (from osprey)

## Request
PROBE retry: executor empty-response root-cause diagnosis via a direct on-box run. task-1792012243084 died with the same disease it was diagnosing (one-shot: finishReason=stop, textLength=0). Do NOT use the one-shot path. Instead run the executor probe directly on yote, capture full stdout/stderr to a file, and diff the transport: one-shot executor vs direct run. Report where the response body is lost.

## Acceptance criteria
1. The request is fully addressed: "PROBE retry: executor empty-response root-cause diagnosis via a direct on-box run. task-1792012243084 died with the same disease it was diagnosing (one-shot: finishReason=stop, textLength=0). Do NOT use the one-shot path. Instead run the executor probe directly on yote, capture full stdout/stderr to".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)