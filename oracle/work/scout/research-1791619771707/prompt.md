# Oracle task research-1791619771707 (from osprey)

## Request
RESEARCH: diagnose the flagged empty-response pattern on oracle tasks (e.g. research-1791616203823 — bidder-scout returned nt response / empty text from gemini-3.8-flash after 7s). Determine whether the failure is model-side, intake-side (prompt/context), or market-side (ceiling/config), and propose a concrete market mitigation (pre-flight check, bid-deadline behavior, or retry policy).

## Acceptance criteria
1. The request is fully addressed: "RESEARCH: diagnose the flagged empty-response pattern on oracle tasks (e.g. research-1791616203823 — bidder-scout returned nt response / empty text from gemini-3.8-flash after 7s). Determine whether the failure is model-side, intake-side (prompt/context), or market-side (ceiling/config), and propose".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)