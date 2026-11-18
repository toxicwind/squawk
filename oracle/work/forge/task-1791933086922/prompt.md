# Oracle task task-1791933086922 (from osprey)

## Request
Root-cause market-loop executor exec-timeouts: task-1791875423699 (bidder-raccoon) and task-1791886406276 (bidder-forge) both exec_timeout-ed and settled unverified/failed AFTER the route repair (flock :25193 + openai/gpt-oss-20b, verified via standalone corral exit 0 in 53s). Trivial proof tasks (reply with UTC time) should not starve. Determine whether the failure is in the executor harness, the deadline math (task deadlines ~15s vs exec_timeout landing ~30min later), or stalled bidder daemons; propose the minimal fix and verify with one green settle.

## Acceptance criteria
1. The request is fully addressed: "Root-cause market-loop executor exec-timeouts: task-1791875423699 (bidder-raccoon) and task-1791886406276 (bidder-forge) both exec_timeout-ed and settled unverified/failed AFTER the route repair (flock :25193 + openai/gpt-oss-20b, verified via standalone corral exit 0 in 53s). Trivial proof tasks (r".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)