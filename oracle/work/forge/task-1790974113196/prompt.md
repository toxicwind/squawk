# Oracle task task-1790974113196 (from ember)

## Request
CANARY-2 (Nightjar): route-health verification. Query http://127.0.0.1:25104/v1/models. Return a JSON object with exactly these keys: http_status (number), model_count (number), eap_present (boolean: true if any model id contains gemini-3.8-flash). Example: {"http_status": 200, "model_count": 42, "eap_present": true}. Return ONLY the JSON object.

## Acceptance criteria
1. The request is fully addressed: "CANARY-2 (Nightjar): route-health verification. Query http://127.0.0.1:25104/v1/models. Return a JSON object with exactly these keys: http_status (number), model_count (number), eap_present (boolean: true if any model id contains gemini-3.8-flash). Example: {"http_status": 200, "model_count": 42, "e".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)