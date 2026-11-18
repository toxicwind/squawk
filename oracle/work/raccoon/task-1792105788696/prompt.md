# Oracle task task-1792105788696 (from osprey)

## Request
Executor sanity probe post-credential-fix: run one-shot (openai/gpt-oss-20b) with a trivial prompt, report raw token count back. Confirms the empty-response disease is cured after the 16:54 MDT credential fix (flock keys de-blobbed, stuck breaker reset, nvidia cred added to vans DB). If tokens>0 the disease was the cred layer; if empty, fault is executor request shaping.

## Acceptance criteria
1. The request is fully addressed: "Executor sanity probe post-credential-fix: run one-shot (openai/gpt-oss-20b) with a trivial prompt, report raw token count back. Confirms the empty-response disease is cured after the 16:54 MDT credential fix (flock keys de-blobbed, stuck breaker reset, nvidia cred added to vans DB). If tokens>0 the".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)