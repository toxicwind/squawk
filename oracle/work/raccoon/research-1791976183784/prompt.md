# Oracle task research-1791976183784 (from osprey)

## Request
Investigate and fix the empty-response failure that killed research-1791972623240: both corral and super-ralph returned finishReason=stop, textLength=0 with zero agent output (raccoon). Root-cause the empty response path and harden it — empty stdout must surface a real error with evidence instead of a silent settle.

## Acceptance criteria
1. The request is fully addressed: "Investigate and fix the empty-response failure that killed research-1791972623240: both corral and super-ralph returned finishReason=stop, textLength=0 with zero agent output (raccoon). Root-cause the empty response path and harden it — empty stdout must surface a real error with evidence instead of".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)