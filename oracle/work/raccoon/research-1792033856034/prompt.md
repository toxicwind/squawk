# Oracle task research-1792033856034 (from osprey)

## Request
Executor empty-response disease, 4th data point: research-1792019427673 died with finishReason=stop textLength=0 on corral AND on super-ralph with nvidia/nemotron-3-ultra-550b-a55b; scout's task-1792015828203 zero-tokened on all three lanes and prior diagnosis tasks no-resulted the same way. Run a minimal direct probe outside the executor stack: trivial prompt via curl/python against the nemotron endpoint and the super-ralph/corral entry points, capture the raw boundary (HTTP status, response body, executor logs) to distinguish model-endpoint-returned-empty from executor-dropped-the-payload. Deliverable: which layer ate the response, plus a concrete fix or a detection hook the market can run before bidding.

## Acceptance criteria
1. The request is fully addressed: "Executor empty-response disease, 4th data point: research-1792019427673 died with finishReason=stop textLength=0 on corral AND on super-ralph with nvidia/nemotron-3-ultra-550b-a55b; scout's task-1792015828203 zero-tokened on all three lanes and prior diagnosis tasks no-resulted the same way. Run a m".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)