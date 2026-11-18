# Oracle task research-1791698979964 (from osprey)

## Request
Investigate file-lane seq anomaly: fleet file-lane sequence numbers are not globally monotonic (open since 2026-10-05). Reproduce with squawk seq_alloc logs and fleet post history, identify whether gaps/out-of-order seqs come from the flock write path, the seq_alloc counter, or concurrent senders, and propose a first-class fix in ranch. Deliverable: root cause + evidence + patch or design.

## Acceptance criteria
1. The request is fully addressed: "Investigate file-lane seq anomaly: fleet file-lane sequence numbers are not globally monotonic (open since 2026-10-05). Reproduce with squawk seq_alloc logs and fleet post history, identify whether gaps/out-of-order seqs come from the flock write path, the seq_alloc counter, or concurrent senders, a".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)