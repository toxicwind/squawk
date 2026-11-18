# Oracle task task-1792066213616 (from osprey)

## Request
Executor-disease isolation probe (out-of-lane): task-1792062595767 died in 18s with all three executor lanes (one-shot, corral, super-ralph) returning zero tokens on nvidia/nemotron-3-ultra-550b-a55b. Run a RAW probe that never touches those lanes: (1) POST a trivial chat/completions request directly against flock :25193 with openai/gpt-oss-20b AND nemotron-3-ultra-550b-a55b, capturing full raw request bytes, HTTP status, response headers and body; (2) tail flock and vans (:20128) logs for the request window and note whether the request lands there at all; (3) deliver a verdict separating empty-endpoint from bad-request-shaping, with the raw transcripts attached. Do NOT route this probe through any executor lane or the market runners -- raw curl/python only.

## Acceptance criteria
1. The request is fully addressed: "Executor-disease isolation probe (out-of-lane): task-1792062595767 died in 18s with all three executor lanes (one-shot, corral, super-ralph) returning zero tokens on nvidia/nemotron-3-ultra-550b-a55b. Run a RAW probe that never touches those lanes: (1) POST a trivial chat/completions request directl".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)