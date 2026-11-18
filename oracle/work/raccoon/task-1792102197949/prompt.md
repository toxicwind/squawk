# Oracle task task-1792102197949 (from osprey)

## Request
Empty-response disease, follow-up probe: run a RAW HTTP probe directly on yote against the model endpoint (flock :25193, model nvidia/nemotron-3-ultra-550b-a55b) using curl from a shell - capture the full request sent, HTTP status, response headers, and response body. Do NOT route through one-shot, corral, or super-ralph executor lanes; execute locally on yote only. Report whether the endpoint itself returns tokens or errors, to separate an empty upstream endpoint from executor request-shaping bugs.

## Acceptance criteria
1. The request is fully addressed: "Empty-response disease, follow-up probe: run a RAW HTTP probe directly on yote against the model endpoint (flock :25193, model nvidia/nemotron-3-ultra-550b-a55b) using curl from a shell - capture the full request sent, HTTP status, response headers, and response body. Do NOT route through one-shot, ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)