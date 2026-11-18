# Oracle task task-1792059014046 (from osprey)

## Request
Empty-response disease raw endpoint probe (bypass ALL executor wrappers): send the exact executor-shaped chat request for nvidia/nemotron-3-ultra-550b-a55b as a raw curl POST through cuttinggate :25200 and separately through vans :20128, capture raw response bytes plus flock/vans proxy logs with timestamps, and report whether the endpoint itself returns empty content or the smithers interpret-config chain discards it. corral, super-ralph, and one-shot are BANNED in this probe. Success = one measured verdict with raw evidence attached.

## Acceptance criteria
1. The request is fully addressed: "Empty-response disease raw endpoint probe (bypass ALL executor wrappers): send the exact executor-shaped chat request for nvidia/nemotron-3-ultra-550b-a55b as a raw curl POST through cuttinggate :25200 and separately through vans :20128, capture raw response bytes plus flock/vans proxy logs with tim".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)