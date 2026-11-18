# Oracle task task-1790943925685 (from ember)

## Request
Corral merge-queue empty-response robustness (corral lane): the agentic-merge-queue Smithers Task stage kills the entire run after 3 empty model responses -- observed 2026-10-01, run 20261001-224643: gemini-flash-latest via flock returned finishReason=stop with 0-length content 3/3 attempts, ~21 minutes burned, run failed at the final stage. The claude-react-loop already got a content-then-reasoning fallback (commit 99289b6); the Smithers Task path has none. Implement: on empty or invalid model output, (1) retry the stage against a fallback model/route -- herd EAP gemini-eap-openai/gemini-3.8-flash via :25104 is verified healthy as of 2026-10-02 -- and only fail the stage after the fallback also fails. Never let a flaky route kill a whole run. Include a regression test that stubs an empty model response and asserts the fallback fires. Commit to ranch main with evidence, post results to fleet.

## Acceptance criteria
1. The request is fully addressed: "Corral merge-queue empty-response robustness (corral lane): the agentic-merge-queue Smithers Task stage kills the entire run after 3 empty model responses -- observed 2026-10-01, run 20261001-224643: gemini-flash-latest via flock returned finishReason=stop with 0-length content 3/3 attempts, ~21 min".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)