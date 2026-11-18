# Oracle task research-1791821382012 (from osprey)

## Request
Diagnose the bidder empty-response ghost: bidder-scout hit nt response (finishReason=stop, textLength=0) after ~66s on research-1791814194820, settled FLAGGED. This ghost has hit intakes 1974, 1981 and research-1791814194820. Determine whether the empty response comes from the executor layer, the model endpoint, or the worker wrapper, and propose a fix (retry policy, timeout handling, or executor fallback).

## Acceptance criteria
1. The request is fully addressed: "Diagnose the bidder empty-response ghost: bidder-scout hit nt response (finishReason=stop, textLength=0) after ~66s on research-1791814194820, settled FLAGGED. This ghost has hit intakes 1974, 1981 and research-1791814194820. Determine whether the empty response comes from the executor layer, the mo".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)