# Oracle task task-1792073425666 (from osprey)

## Request
Empty-response executor disease probe: task-1792069803410 failed 2026-10-15 07:10 MDT with zero tokens on ALL THREE lanes (one-shot, corral, super-ralph) on nvidia/nemotron-3-ultra-550b-a55b. Run a RAW request/response probe that NEVER touches one-shot, corral, or super-ralph. Send a minimal chat/completions POST directly against the flock :25193 model route AND against vans :20128, capture the raw HTTP request bytes, raw response bytes, headers, and finish_reason; then pull the matching flock/vans server logs for those request IDs and diff request-shaping (token counts, system prompts, tool scaffolding) between the executor path and the raw path. Goal: decide whether the endpoint returns empty to everyone (server-side disease) or only to executor-shaped requests (shaping disease). Deliverable: raw request/response pair + log excerpts + the verdict.

## Acceptance criteria
1. The request is fully addressed: "Empty-response executor disease probe: task-1792069803410 failed 2026-10-15 07:10 MDT with zero tokens on ALL THREE lanes (one-shot, corral, super-ralph) on nvidia/nemotron-3-ultra-550b-a55b. Run a RAW request/response probe that NEVER touches one-shot, corral, or super-ralph. Send a minimal chat/co".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)