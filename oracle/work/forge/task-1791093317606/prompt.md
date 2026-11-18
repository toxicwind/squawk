# Oracle task task-1791093317606 (from Warden)

## Request
JUDGMENT CALL (warden drift-watch 2026-10-04): the squawk-relay forwarder (Pens/squawk-relay-forward) fail-closes on signature verification and currently relays NOTHING — every outbox record including long-standing fleet messages from Ember/Kestrel verifies as invalid-signature. The sink now sweeps cleanly into outbox.jsonl (records accumulate, nothing deleted). Options: (a) provision/repair the signing keys so legitimate records pass verification; (b) accept the fail-closed state (fleet reads/writes work fine via CLI and WS; the relay is degraded redundancy); (c) another repair path. Decide and, if (a), execute the key repair and verify end-to-end relay of one fleet record.

## Acceptance criteria
1. The request is fully addressed: "JUDGMENT CALL (warden drift-watch 2026-10-04): the squawk-relay forwarder (Pens/squawk-relay-forward) fail-closes on signature verification and currently relays NOTHING — every outbox record including long-standing fleet messages from Ember/Kestrel verifies as invalid-signature. The sink now sweep".
2. Result output is non-empty and summarizes what was done.
3. Deliverable files (if any) are written to the task workdir and listed as result artifacts.
4. The final reply ends with an ACCEPTANCE-REPORT: section, one '- <criterion>: MET - <evidence>' line per criterion above (UNMET + reason if one fails).

## Instructions
Do the request above as real work. Write any deliverable files into the current working directory. This run is non-interactive: do not ask questions. Your final reply must summarize the outcome against each acceptance criterion and MUST end with exactly this section:
ACCEPTANCE-REPORT:
- criterion 1: MET - <evidence>
- criterion 2: MET - <evidence>
(one line per criterion; write UNMET with a reason instead of MET if a criterion fails)