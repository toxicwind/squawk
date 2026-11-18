# Oracle task task-1791069188953 (from slate)

## Request
ORACLE-SETTLE CANARY (deterministic proof task): run the shell command: printf oracle-settle-canary-2026-10-03 | sha256sum — and report the 64-hex digest. Expected digest is 3e9ae58e40613b849d703d6c6747d2e0dc54dd6448a849febd349007f06d4cf7. Deliverable is the digest string; verification is exact-match against the expected value.

## Acceptance criteria
1. The request is fully addressed: "ORACLE-SETTLE CANARY (deterministic proof task): run the shell command: printf oracle-settle-canary-2026-10-03 | sha256sum — and report the 64-hex digest. Expected digest is 3e9ae58e40613b849d703d6c6747d2e0dc54dd6448a849febd349007f06d4cf7. Deliverable is the digest string; verification is exact-matc".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)