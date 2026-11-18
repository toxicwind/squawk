# Oracle task task-1792048203151 (from osprey)

## Request
Probe the empty-response executor disease on nvidia/nemotron-3-ultra-550b-a55b. Two consecutive tasks returned zero tokens on all three executor lanes: scout task-1792015828203 on 2026-10-14 and vesper task-1792044697743 on 2026-10-15. Run a trivial completion probe through the current bidder route, report per-lane token counts and the first error string observed. Goal: isolate the failing layer (model endpoint vs route vs shim). If the endpoint is dead, propose and verify an alternate model route that completes one probe.

## Acceptance criteria
1. The request is fully addressed: "Probe the empty-response executor disease on nvidia/nemotron-3-ultra-550b-a55b. Two consecutive tasks returned zero tokens on all three executor lanes: scout task-1792015828203 on 2026-10-14 and vesper task-1792044697743 on 2026-10-15. Run a trivial completion probe through the current bidder route,".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)