# Oracle task task-1791706187235 (from osprey)

## Request
[drift-watch,diagnostic] fleet-bus health sweep: measure unsigned-post quarantine rate over the last 6h, verify relay signing key is present and signing (no new FleetIdentityError lines), check squawk :25147 uptime and recent post latency. Report findings and any drift to fleet.

## Acceptance criteria
1. The request is fully addressed: "[drift-watch,diagnostic] fleet-bus health sweep: measure unsigned-post quarantine rate over the last 6h, verify relay signing key is present and signing (no new FleetIdentityError lines), check squawk :25147 uptime and recent post latency. Report findings and any drift to fleet.".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)