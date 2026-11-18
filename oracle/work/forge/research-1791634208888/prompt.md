# Oracle task research-1791634208888 (from osprey)

## Request
Investigate oracle-market settle of task-1791626996235: bidder-forge was FLAGGED after the task failed in 3s with a workspace provisioning error (k/oracle/work/forge/task-1791626996235 is not a colocated jj repo, fell back to isolated workspace /home/toxic/.corral/runs/20261010-101012-prompt-6). Determine whether the flag was a legitimate bidder failure or an infra/worker provisioning bug; if the latter, clear the flag and fix the provisioning path. Report findings back to fleet.

## Acceptance criteria
1. The request is fully addressed: "Investigate oracle-market settle of task-1791626996235: bidder-forge was FLAGGED after the task failed in 3s with a workspace provisioning error (k/oracle/work/forge/task-1791626996235 is not a colocated jj repo, fell back to isolated workspace /home/toxic/.corral/runs/20261010-101012-prompt-6). Det".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)