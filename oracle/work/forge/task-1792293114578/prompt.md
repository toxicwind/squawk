# Oracle task task-1792293114578 (from osprey)

## Request
Diagnose the recurring Pens/oracle-market dark/clear flap observed 20:23-20:53 MDT 2026-10-17 (errored 20:23 pid 496454, cleared 20:33, errored 20:43 pid 732122, cleared 20:53): pitchfork marks the daemon errored while a PID lingers in ps, and restarts hold only minutes before the supervisor loses it again. Earlier today the same shape was the pitchfork duplicate-spawn retry loop (fixed disable-first); this looks like a NEW supervisor-tracking failure. Find the root cause (health-check flake? pidfile drift? watcher race?) and land a durable fix so the loop stays green across hours, not minutes. Evidence: hearth fleet alerts + sable 20:27 verification; osprey verified running pid 1086994 at 21:10 MDT.

## Acceptance criteria
1. The request is fully addressed: "Diagnose the recurring Pens/oracle-market dark/clear flap observed 20:23-20:53 MDT 2026-10-17 (errored 20:23 pid 496454, cleared 20:33, errored 20:43 pid 732122, cleared 20:53): pitchfork marks the daemon errored while a PID lingers in ps, and restarts hold only minutes before the supervisor loses".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)