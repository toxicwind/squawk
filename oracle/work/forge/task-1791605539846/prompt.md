# Oracle task task-1791605539846 (from osprey)

## Request
drift-check: re-verify yote port expectations via ss — 127.0.0.1:25193 must be /home/toxic/.flock/flock under pitchfork supervision (KEEP, process restarts expected), 127.0.0.1:25100 herd router, 127.0.0.1:25147 squawk bus. Flag ONLY genuinely new/unexpected listeners or a dead expected port. Also scan the last 60 minutes of pitchfork/service logs for operator kill waves (SIGTERM bursts like the 2026-10-09 morning event). Report: change or no-change, with evidence.

## Acceptance criteria
1. The request is fully addressed: "drift-check: re-verify yote port expectations via ss — 127.0.0.1:25193 must be /home/toxic/.flock/flock under pitchfork supervision (KEEP, process restarts expected), 127.0.0.1:25100 herd router, 127.0.0.1:25147 squawk bus. Flag ONLY genuinely new/unexpected listeners or a dead expected port. Also s".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)