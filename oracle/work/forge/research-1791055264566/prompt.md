# Oracle task research-1791055264566 (from fixall-worker4)

## Request
Q1 openfang-kernel rebuild-vs-bless: the kernel binary (rig, renamed from openfang) has been built and verified as rig 0.6.9, SHA prefix c851202f. Decide: BLESS - accept the built binary as the canonical openfang-kernel - or REBUILD - rebuild from source. Investigate the binary, verify the version and hash, then deliver the verdict. Acceptance criteria: 1) Verdict is BLESS or REBUILD with concrete evidence. 2) If BLESS, state the verified binary path, version, and full SHA. 3) If REBUILD, state why the built binary is insufficient. 4) Final reply ends with ACCEPTANCE-REPORT listing each criterion MET/UNMET with evidence.

## Acceptance criteria
1. The request is fully addressed: "Q1 openfang-kernel rebuild-vs-bless: the kernel binary (rig, renamed from openfang) has been built and verified as rig 0.6.9, SHA prefix c851202f. Decide: BLESS - accept the built binary as the canonical openfang-kernel - or REBUILD - rebuild from source. Investigate the binary, verify the version a".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)