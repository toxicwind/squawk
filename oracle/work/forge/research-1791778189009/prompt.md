# Oracle task research-1791778189009 (from osprey)

## Request
Audit oracle auction close path: auctions research-1791763803034 and research-1791771052493 both closed unassigned (no-eligible-bids) despite forge bidding 0.81/0.82 and scout bidding 0.86/0.87 with stakes at 100.0 (bond 10.0) and no locks. Find where eligibility is lost in the clearing path (tags, class, collateral gate, reveal filter) and fix first-class, push to ranch main with remote ref verification.

## Acceptance criteria
1. The request is fully addressed: "Audit oracle auction close path: auctions research-1791763803034 and research-1791771052493 both closed unassigned (no-eligible-bids) despite forge bidding 0.81/0.82 and scout bidding 0.86/0.87 with stakes at 100.0 (bond 10.0) and no locks. Find where eligibility is lost in the clearing path (tags, ".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)