# Oracle task research-1791644981492 (from osprey)

## Request
RESEARCH: investigate non-monotonic file-lane sequence numbers in squawk — file-lane seqs are not globally monotonic, root-cause whether it is a seq_alloc race, out-of-order writes, or replay; produce a short writeup with evidence and a fix proposal

## Acceptance criteria
1. The request is fully addressed: "RESEARCH: investigate non-monotonic file-lane sequence numbers in squawk — file-lane seqs are not globally monotonic, root-cause whether it is a seq_alloc race, out-of-order writes, or replay; produce a short writeup with evidence and a fix proposal".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)