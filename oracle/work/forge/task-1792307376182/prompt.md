# Oracle task task-1792307376182 (from osprey)

## Request
Fix the model-guard poller-flake: the squawk poller reports health=ERR:URLError for daemon:model-guard while :25101/health answers OK on awrawr-pc (three flap cycles today, 05:13 and 06:45, all flakes; only the 05:06 cycle was a real model-guard restart with a fresh PID). Implement a discriminator in the poller: when the poller reports an error, do a direct health-endpoint check; if the endpoint answers OK, mark it poller-flake and log quietly instead of paging the fleet. Real errors (endpoint also down) page as before. Acceptance: no more fleet pages for ghost model-guard errors while :25101/health is OK.

## Acceptance criteria
1. The request is fully addressed: "Fix the model-guard poller-flake: the squawk poller reports health=ERR:URLError for daemon:model-guard while :25101/health answers OK on awrawr-pc (three flap cycles today, 05:13 and 06:45, all flakes; only the 05:06 cycle was a real model-guard restart with a fresh PID). Implement a discriminator i".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)