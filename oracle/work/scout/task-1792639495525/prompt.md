# Oracle task task-1792639495525 (from main)

## Request
PROBE verify GHAS search: curl -s 'http://127.0.0.1:25112/api/search?query=robot&categories=repositories&per_page=2' and print the HTTP result/repo names. Trivial one-command probe.

## Acceptance criteria
1. The request is fully addressed: "PROBE verify GHAS search: curl -s 'http://127.0.0.1:25112/api/search?query=robot&categories=repositories&per_page=2' and print the HTTP result/repo names. Trivial one-command probe.".
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