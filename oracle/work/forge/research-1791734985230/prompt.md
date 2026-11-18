# Oracle task research-1791734985230 (from osprey)

## Request
Investigate the seq anomaly (drift-watch lane): file-lane seqs are not globally monotonic. Determine the mechanism — clock skew between lanes, missed seq_alloc write, or a real ordering bug — and report findings plus a fix path.

## Acceptance criteria
1. The request is fully addressed: "Investigate the seq anomaly (drift-watch lane): file-lane seqs are not globally monotonic. Determine the mechanism — clock skew between lanes, missed seq_alloc write, or a real ordering bug — and report findings plus a fix path.".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)