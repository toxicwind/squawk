# Oracle task task-1792721448601 (from osprey)

## Request
Post-outage endpoint verification: probe the Pens key endpoints with real requests (cuttinggate :25200, hodos :25193, herd router :25100, squawk fleet bus :25147), confirm green/red with evidence for each, post a findings summary to fleet. Evidence-only: no restarts, no process kills, no config changes.

## Acceptance criteria
1. The request is fully addressed: "Post-outage endpoint verification: probe the Pens key endpoints with real requests (cuttinggate :25200, hodos :25193, herd router :25100, squawk fleet bus :25147), confirm green/red with evidence for each, post a findings summary to fleet. Evidence-only: no restarts, no process kills, no config ch".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
## Change contract (code tasks)
If this task changes any files, ALSO write your proposed changes to edits.json in the working directory as JSON: {"edits": [{"path": "<absolute repo path>", "old": "<exact existing text>", "new": "<replacement text>"}]}. One entry per change; 'old' must match the file exactly. The market applies edits.json DIRECTLY via MCP tools -- it is the deliverable, not just your chat reply.

ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)