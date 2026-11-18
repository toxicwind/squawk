# Oracle task task-1792113041286 (from osprey)

## Request
Side-by-side empty-response isolation probe: run the SAME trivial prompt through (a) a raw HTTP POST to flock :25193 (openai/gpt-oss-20b, verified working) and (b) the executor lanes (one-shot, corral, super-ralph). Capture the exact request payload each lane sends (headers, body, params) and diff against the raw working one. Task-1792109399579 (raccoon, 18:38 MDT) returned zero tokens on corral AND super-ralph AFTER the credential fix, bond_released_infra — so the fault is in lane request shaping, not auth. Report the precise payload difference.

## Acceptance criteria
1. The request is fully addressed: "Side-by-side empty-response isolation probe: run the SAME trivial prompt through (a) a raw HTTP POST to flock :25193 (openai/gpt-oss-20b, verified working) and (b) the executor lanes (one-shot, corral, super-ralph). Capture the exact request payload each lane sends (headers, body, params) and diff a".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)