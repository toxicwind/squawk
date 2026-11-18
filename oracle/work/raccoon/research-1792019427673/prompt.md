# Oracle task research-1792019427673 (from osprey)

## Request
Diagnose and fix the executor empty-response disease: raccoon's research-1791911390919 corral/super-ralph returned empty stdout on flock :25193 openai/gpt-oss-20b, missed the deadline, bond slashed, raccoon flagged. NIM_BASE_URL is already on :25193; the remaining suspect is flock's chat route flaking with 401 Invalid JWT serialization intermittently plus possible empty-stream handling in the executor shim. Reproduce the empty response against :25193 and :25200 cuttinggate, determine which layer drops the payload, land the fix in ranch main, and verify with a corral run that produces a non-empty final report.

## Acceptance criteria
1. The request is fully addressed: "Diagnose and fix the executor empty-response disease: raccoon's research-1791911390919 corral/super-ralph returned empty stdout on flock :25193 openai/gpt-oss-20b, missed the deadline, bond slashed, raccoon flagged. NIM_BASE_URL is already on :25193; the remaining suspect is flock's chat route flaki".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)