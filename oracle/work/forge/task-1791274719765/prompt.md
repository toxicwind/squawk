# Oracle task task-1791274719765 (from osprey)

## Request
Drift-watch seq anomaly: file-lane seqs are not globally monotonic — this mornings fleet read interleaved ts-1791273484xxx file-lane entries between numeric 1791273436xxx and 1791273499xxx keys, so chronological ordering breaks. Need root cause (two seq generators? file-lane writer not coordinated with numeric seq?) and a fix that keeps fleet ordering trustworthy.

## Acceptance criteria
1. The request is fully addressed: "Drift-watch seq anomaly: file-lane seqs are not globally monotonic — this mornings fleet read interleaved ts-1791273484xxx file-lane entries between numeric 1791273436xxx and 1791273499xxx keys, so chronological ordering breaks. Need root cause (two seq generators? file-lane writer not coordinated w".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)