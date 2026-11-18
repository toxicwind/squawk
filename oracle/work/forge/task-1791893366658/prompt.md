# Oracle task task-1791893366658 (from osprey)

## Request
Retry biddable task-1791889763475 through cuttinggate :25200 instead of flock :25193: flock chat route has been flaky (ok alternating with 401 Invalid JWT) and corral/super-ralph keeps returning empty responses that fail the settle. Target: one verified settle with non-empty JSON output; report which lane succeeded and capture the raw agent output on failure.

## Acceptance criteria
1. The request is fully addressed: "Retry biddable task-1791889763475 through cuttinggate :25200 instead of flock :25193: flock chat route has been flaky (ok alternating with 401 Invalid JWT) and corral/super-ralph keeps returning empty responses that fail the settle. Target: one verified settle with non-empty JSON output; report whic".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)