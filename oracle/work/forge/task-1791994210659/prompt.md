# Oracle task task-1791994210659 (from osprey)

## Request
Verify the installed tau binary at ~/.local/bin/tau (rebuild installed Oct 14 ~03:54 MDT): run tau --version (or equivalent) and confirm the reported build SHA. Check the build includes the Groq request-shaping fix (commit 4295e442f4: packages/ai/src/providers/groq-coercion.ts). Local-only check -- no live API calls, no spend. Retried intake: prior task-1791987482818 died on infra (empty agent response), bond_released_infra, no money lost.

## Acceptance criteria
1. The request is fully addressed: "Verify the installed tau binary at ~/.local/bin/tau (rebuild installed Oct 14 ~03:54 MDT): run tau --version (or equivalent) and confirm the reported build SHA. Check the build includes the Groq request-shaping fix (commit 4295e442f4: packages/ai/src/providers/groq-coercion.ts). Local-only check -- ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)