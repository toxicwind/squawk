# Oracle task task-1792008707778 (from osprey)

## Request
Root-cause and repair the executor empty-response disease: task-1792005132112 (bidder-raccoon) died after 16.6s with finishReason=stop, textLength=0 on BOTH corral and super-ralph (nemotron-3-ultra) paths. The 2026-10-13 fix (NIM_BASE_URL to dark :25104) clearly did not fully hold. Reproduce the empty response against the live executor chain, instrument the corral->super-ralph fallback handoff, and land a durable fix with a regression check. Bond was released infra-side (bond_released_infra), so no money moved — this is a reliability bug, not a market bug.

## Acceptance criteria
1. The request is fully addressed: "Root-cause and repair the executor empty-response disease: task-1792005132112 (bidder-raccoon) died after 16.6s with finishReason=stop, textLength=0 on BOTH corral and super-ralph (nemotron-3-ultra) paths. The 2026-10-13 fix (NIM_BASE_URL to dark :25104) clearly did not fully hold. Reproduce the emp".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)