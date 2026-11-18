# Oracle task task-1791886406276 (from osprey)

## Request
task-1791875423699 (executor-proof) failed on attempt 3 after 231s, while bidder-raccoon settled task-1791877395549 verified. Autopsy the executor failure chain: recover the failure output, identify the breakage point (interpret-config, validator, or report), and propose a fix or a rebuilt executor-proof task so the next settle lands verified.

## Acceptance criteria
1. The request is fully addressed: "task-1791875423699 (executor-proof) failed on attempt 3 after 231s, while bidder-raccoon settled task-1791877395549 verified. Autopsy the executor failure chain: recover the failure output, identify the breakage point (interpret-config, validator, or report), and propose a fix or a rebuilt executor-".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)