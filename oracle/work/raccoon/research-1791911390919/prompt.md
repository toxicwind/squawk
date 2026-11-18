# Oracle task research-1791911390919 (from osprey)

## Request
Diagnose the corral/super-ralph empty-response failure seen in research-1791907797273: corral hit INV-002 (no valid JSON in agent response, finishReason) and super-ralph also failed after 8+ min on investigate-empty-response-root-cause. Determine whether the root cause is flock chat-route flakiness (the known gpt-oss-20b 401 Invalid JWT serialization alternation on :25193), the corral interpret-config JSON parsing being too strict, or the agent response handling architecture itself. Deliver a minimal reproducible probe against :25193 and :25200, a verdict naming the layer at fault, and the smallest fix that keeps research tasks settling.

## Acceptance criteria
1. The request is fully addressed: "Diagnose the corral/super-ralph empty-response failure seen in research-1791907797273: corral hit INV-002 (no valid JSON in agent response, finishReason) and super-ralph also failed after 8+ min on investigate-empty-response-root-cause. Determine whether the root cause is flock chat-route flakiness ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)