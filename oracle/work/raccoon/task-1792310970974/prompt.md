# Oracle task task-1792310970974 (from osprey)

## Request
Fix the corral workdir provisioning bug: task workdir setup fails with "not a colocated jj repo" (observed on task-1792307376182, which died on this before super-ralph even ran). Repro the failure, locate the provisioning code path, fix it, and verify a corral attempt actually launches. Report back to fleet with the commit.

## Acceptance criteria
1. The request is fully addressed: "Fix the corral workdir provisioning bug: task workdir setup fails with "not a colocated jj repo" (observed on task-1792307376182, which died on this before super-ralph even ran). Repro the failure, locate the provisioning code path, fix it, and verify a corral attempt actually launches. Report back ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)