# Oracle task task-1791275140753 (from osprey)

## Request
Smoke-test the corral smithers CLI resolution fix (ranch main 0917990): invoke runWorkflow with a minimal no-op prompt and confirm the CLI path now resolves to node_modules/smthrs/src/bin/smithers.js instead of throwing smithers package not found. Report the resolved path and how far the workflow gets.

## Acceptance criteria
1. The request is fully addressed: "Smoke-test the corral smithers CLI resolution fix (ranch main 0917990): invoke runWorkflow with a minimal no-op prompt and confirm the CLI path now resolves to node_modules/smthrs/src/bin/smithers.js instead of throwing smithers package not found. Report the resolved path and how far the workflow ge".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)