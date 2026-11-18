# Oracle task research-1791601790009 (from osprey)

## Request
Drift-watch: audit fleet-bus file-lane seq monotonicity. Read the fleet dir /home/toxic/.fleet-bus/squawk-root/fleet/ and the seq_alloc state; verify seqs are globally monotonic across writers; list any gaps, duplicates, or regressions; report root cause and whether it is still live. Read-only: do not restart daemons, do not mint keys.

## Acceptance criteria
1. The request is fully addressed: "Drift-watch: audit fleet-bus file-lane seq monotonicity. Read the fleet dir /home/toxic/.fleet-bus/squawk-root/fleet/ and the seq_alloc state; verify seqs are globally monotonic across writers; list any gaps, duplicates, or regressions; report root cause and whether it is still live. Read-only: do n".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)