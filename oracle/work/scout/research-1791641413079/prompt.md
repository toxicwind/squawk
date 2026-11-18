# Oracle task research-1791641413079 (from osprey)

## Request
Investigate the fleet file-lane sequence anomaly: file-lane sends receive seqs (e.g. 1790987986210) far BELOW already-served feed-lane seqs (e.g. 1791169060739), so file-lane seqs are not globally monotonic. Find where seq_alloc/seq assignment diverges between the file-lane write path and the raced feed view, confirm the root cause with a live repro, and propose the fix (code patch, not docs). Tags: code-fix, research.

## Acceptance criteria
1. The request is fully addressed: "Investigate the fleet file-lane sequence anomaly: file-lane sends receive seqs (e.g. 1790987986210) far BELOW already-served feed-lane seqs (e.g. 1791169060739), so file-lane seqs are not globally monotonic. Find where seq_alloc/seq assignment diverges between the file-lane write path and the raced ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)