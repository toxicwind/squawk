# Oracle task task-1792812234324 (from Vesper (Kite crew))

## Request
PROBE (T2 bidder-chain proof): Verify that Pens/thresher intentionally serves :25127. Gather three evidence lines: (1) pitchfork status of Pens/thresher, (2) the process command line listening on 25127, (3) one curl of http://127.0.0.1:25127/ first line. Deliverable: post the three lines with a one-line verdict to fleet. This is a bounded probe task with a checkable artifact.

## Acceptance criteria
1. The request is fully addressed: "PROBE (T2 bidder-chain proof): Verify that Pens/thresher intentionally serves :25127. Gather three evidence lines: (1) pitchfork status of Pens/thresher, (2) the process command line listening on 25127, (3) one curl of http://127.0.0.1:25127/ first line. Deliverable: post the three lines with a ".
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