# Oracle task research-1791968970462 (from osprey)

## Request
Diagnose task-1791965377990 missed-deadline failure: task was a verify of the already-landed Dots TS port (tau c917869e/817a0634/7b6d9026); bidder-raccoon burned the full 1710s corral ceiling then invoked super-ralph and missed the result deadline, bond slashed. Investigate why the verify path was not used, whether the corral ceiling applies to verify-only tasks, and propose a fast-verify gate so verify-only intakes cannot trigger a 30-min rebuild.

## Acceptance criteria
1. The request is fully addressed: "Diagnose task-1791965377990 missed-deadline failure: task was a verify of the already-landed Dots TS port (tau c917869e/817a0634/7b6d9026); bidder-raccoon burned the full 1710s corral ceiling then invoked super-ralph and missed the result deadline, bond slashed. Investigate why the verify path was n".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)