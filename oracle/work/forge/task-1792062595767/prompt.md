# Oracle task task-1792062595767 (from osprey)

## Request
Empty-response executor disease: build a raw wire probe that never touches one-shot, corral, or super-ralph. Send a minimal OpenAI-compatible chat-completions request with the exact same model route the executors use (flock :25193 -> vans :20128, openai/gpt-oss-20b or nvidia/nemotron-3-ultra), capture raw HTTP request bytes, raw response bytes (headers + body, no parsing), and tail the flock and vans server logs for the matching request window. Verdict must answer one question: does the endpoint itself return empty (finishReason=stop, zero text at the wire), or do the executor lanes mangle/shape the request into emptiness? Publish the raw artifacts (request.txt, response.txt, log excerpts) with the result.

## Acceptance criteria
1. The request is fully addressed: "Empty-response executor disease: build a raw wire probe that never touches one-shot, corral, or super-ralph. Send a minimal OpenAI-compatible chat-completions request with the exact same model route the executors use (flock :25193 -> vans :20128, openai/gpt-oss-20b or nvidia/nemotron-3-ultra), captu".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)