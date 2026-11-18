# Oracle task task-1791274817344 (from osprey)

## Request
Fix oracle corral workspace provisioning for forge tasks: task-1791274719765 failed after 1s because /home/toxic/pens/Pens/ranch/squawk/oracle/work/forge/ is not a colocated jj repo (no .jj or .git at work root; task dirs are plain dirs holding only prompt.md and ralph-invocation.txt). Corral fell back to an isolated workspace and the task still died. Either provision jj-colocated workspaces as corral expects, or make the isolated-workspace fallback path actually execute the task end to end.

## Acceptance criteria
1. The request is fully addressed: "Fix oracle corral workspace provisioning for forge tasks: task-1791274719765 failed after 1s because /home/toxic/pens/Pens/ranch/squawk/oracle/work/forge/ is not a colocated jj repo (no .jj or .git at work root; task dirs are plain dirs holding only prompt.md and ralph-invocation.txt). Corral fell back".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)