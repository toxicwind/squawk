# Oracle task task-1791896971325 (from osprey)

## Request
executor smoke task: verify the fixed chain end-to-end — bidder runs a minimal corral/smithers job routed through flock :25193 with model openai/gpt-oss-20b and must return a non-empty result. Pass = interpret-config and final-report complete. This follows forge flagged on task-1791893366658 with an empty response; the point is to prove the no-result disease is cleared, not to retry that task.

## Acceptance criteria
1. The request is fully addressed: "executor smoke task: verify the fixed chain end-to-end — bidder runs a minimal corral/smithers job routed through flock :25193 with model openai/gpt-oss-20b and must return a non-empty result. Pass = interpret-config and final-report complete. This follows forge flagged on task-1791893366658 with an".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)