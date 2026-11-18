# Oracle task research-1791814194820 (from osprey)

## Request
Reproduce and root-cause the 66s empty-response ghost: smithers-invoked workers (e.g. research-1791807017010) fail after ~66-70s with finishReason=stop and textLength=0, empty agent response. Intakes 1974 and 1981 hit the same wall. Reproduce it against the Pens-scripts router on yote, capture request/response logs at the model invocation boundary, and land a fix or a mitigation (retry-with-backoff on empty response) in the ranch repo with tests, then push to toxicwind/ranch main.

## Acceptance criteria
1. The request is fully addressed: "Reproduce and root-cause the 66s empty-response ghost: smithers-invoked workers (e.g. research-1791807017010) fail after ~66-70s with finishReason=stop and textLength=0, empty agent response. Intakes 1974 and 1981 hit the same wall. Reproduce it against the Pens-scripts router on yote, capture request/".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)