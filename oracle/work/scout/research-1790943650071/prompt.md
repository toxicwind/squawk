# Oracle task research-1790943650071 (from ember)

## Request
ts-migration Tier-0 audit (Forge lane): for each of keypool, model-guard, squawk-ws, awrawr-mcp, report current runtime (Python vs Bun/TS, with evidence from the live process table and the repo), migration blockers if any, and nominate the single next migration target with a concrete plan (files to port, test gate, rollback). Note: brand is deprecated into flicker as of 2026-09-30 -- update the Tier-1 list to drop brand and note flicker status. Deliverable: audit report with evidence plus nomination, posted to fleet.

## Acceptance criteria
1. The request is fully addressed: "ts-migration Tier-0 audit (Forge lane): for each of keypool, model-guard, squawk-ws, awrawr-mcp, report current runtime (Python vs Bun/TS, with evidence from the live process table and the repo), migration blockers if any, and nominate the single next migration target with a concrete plan (files to ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)