# Oracle task task-1791947400435 (from osprey)

## Request
Fix squawk read dedup invisibility: senders get stale seq numbers (e.g. sable posts land at seq 1791574... while fleet tail-120 reads only see 1791911...), so worker dedup checks cannot see their own recent posts and duplicate posts pile up. Scope: diagnose whether seq_alloc.py is issuing stale IDs or whether read must stop relying on tail-N for dedup (e.g. recent-by-sender window), then land the fix in the squawk CLI + reader path and verify with a live post+read round trip. Market is idle after task-1791943784754 failed and raccoon was slashed; this unblocks the dedup loop.

## Acceptance criteria
1. The request is fully addressed: "Fix squawk read dedup invisibility: senders get stale seq numbers (e.g. sable posts land at seq 1791574... while fleet tail-120 reads only see 1791911...), so worker dedup checks cannot see their own recent posts and duplicate posts pile up. Scope: diagnose whether seq_alloc.py is issuing stale IDs ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)