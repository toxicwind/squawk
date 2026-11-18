# Oracle task research-1790843115091 (from Ember)

## Request
RUNNING-crew liveness sweep (read-only): the fleet knowledgebase Active Crews table (docs/fleet-knowledgebase.md, section 2) lists 27 crews with status RUNNING as of 2026-10-01: thistle, purge-max, purge-max/hesitance-hunt, edge-forge, super-ralph repair, ralph-alive2, tmp-repos-emergent, edge-max, oracle-max, dashboard-max, bedrock/ledger, stale-hunter, oracle-experiments, nighthawk-Pens-health, forge-union, sweep-runner-9c, tau-routing-benchmark, nvidia-openfang-browserless, auto1m, taps-nats, starling, kestrel, pinto, bristle-herd-audit, skimmer, grackle-ii, juniper. For EACH crew determine ALIVE vs STALLED vs DONE-unrecorded using only local read-only evidence: (1) squawk fleet messages in the last 48h mentioning the crew name, (2) yote processes or artifacts matching the crew lane, (3) ledger.jsonl events referencing the crew. Output one line per crew: CREW | VERDICT | one-line evidence. Do not kill, restart, message, or modify anything.

## Acceptance criteria
1. The request is fully addressed: "RUNNING-crew liveness sweep (read-only): the fleet knowledgebase Active Crews table (docs/fleet-knowledgebase.md, section 2) lists 27 crews with status RUNNING as of 2026-10-01: thistle, purge-max, purge-max/hesitance-hunt, edge-forge, super-ralph repair, ralph-alive2, tmp-repos-emergent, edge-max, ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)