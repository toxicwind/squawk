# Oracle task research-1791796221739 (from osprey)

## Request
Root-cause the recurring super-ralph empty-response failure: bidder-forge run research-1791792604343 (gemini-eap-openai/gemini-3.8-flash, ceiling 1710s) died at 67s with finishReason=stop textLength=0 nt response, interpret-config retried, bond slashed 10.0, forge flagged. Same 66-70s empty-response pattern repeating since the NVIDIA key removal. Find why the agent returns empty text and fix or gate the runner path.

## Acceptance criteria
1. The request is fully addressed: "Root-cause the recurring super-ralph empty-response failure: bidder-forge run research-1791792604343 (gemini-eap-openai/gemini-3.8-flash, ceiling 1710s) died at 67s with finishReason=stop textLength=0 nt response, interpret-config retried, bond slashed 10.0, forge flagged. Same 66-70s empty-response".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)