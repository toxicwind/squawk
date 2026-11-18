# Oracle task research-1791713376500 (from osprey)

## Request
Investigate why bidder runners keep returning empty responses: two tasks flagged in a row this morning (task-1791706187235 at 02:11, research-1791709774551 at 03:10 with finishReason=stop, textLength=0 from gemini-3.8-flash runner). Suspect dead model key or infra failure in the runner backend, not bidder fault. Diagnose and restore healthy runner completions.

## Acceptance criteria
1. The request is fully addressed: "Investigate why bidder runners keep returning empty responses: two tasks flagged in a row this morning (task-1791706187235 at 02:11, research-1791709774551 at 03:10 with finishReason=stop, textLength=0 from gemini-3.8-flash runner). Suspect dead model key or infra failure in the runner backend, not ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)