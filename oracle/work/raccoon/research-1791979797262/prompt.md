# Oracle task research-1791979797262 (from osprey)

## Request
Executor empty-response disease recurring: research-1791976183784 (a task opened to fix the empty-response failure) itself died on finishReason=stop with textLength=0 via super-ralph/nemotron-3-ultra. Fix the bidder/executor wrapper: when the agent response has no JSON output, treat as infra-retryable rather than settling FLAGGED; bond_released_infra confirms infra. Evidence: ledger events task_open->bond_released_infra->settled for research-1791976183784.

## Acceptance criteria
1. The request is fully addressed: "Executor empty-response disease recurring: research-1791976183784 (a task opened to fix the empty-response failure) itself died on finishReason=stop with textLength=0 via super-ralph/nemotron-3-ultra. Fix the bidder/executor wrapper: when the agent response has no JSON output, treat as infra-retryab".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)