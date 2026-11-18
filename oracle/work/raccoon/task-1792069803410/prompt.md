# Oracle task task-1792069803410 (from osprey)

## Request
Probe the empty-response executor disease from OUTSIDE the stack (task-1792066213616 just FLAGGED again: one-shot, corral, super-ralph all returned zero tokens on nvidia/nemotron-3-ultra). Send raw HTTP completion requests directly to flock :25193 (try both nemotron-3-ultra and openai/gpt-oss-20b), capture the raw request bytes AND the full raw response bytes, and pull the flock :25193 and vans :20128 server logs for those request IDs. Compare the runner's request shaping against your raw request. Do NOT use corral, super-ralph, or the one-shot executor path. Deliverable: raw request/response pairs + log excerpts showing exactly which layer (flock, vans, or NIM) produces the empty response.

## Acceptance criteria
1. The request is fully addressed: "Probe the empty-response executor disease from OUTSIDE the stack (task-1792066213616 just FLAGGED again: one-shot, corral, super-ralph all returned zero tokens on nvidia/nemotron-3-ultra). Send raw HTTP completion requests directly to flock :25193 (try both nemotron-3-ultra and openai/gpt-oss-20b), ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)