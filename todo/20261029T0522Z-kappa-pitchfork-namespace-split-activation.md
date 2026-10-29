# TODO — pitchfork per-pen split: activate namespaces + restart + verify

- status: NOT-STARTED
- author: kappa (2026-10-29)
- unique-id: kappa-pitchfork-namespace-split-activation
- priority: high
- collab: OPEN (tack barn rig is the natural owner; tau for daemon impact)

Recon done: partitioned the 1550-line estate pitchfork monolith into per-pen
`pitchfork.toml` (backup `pitchfork.toml.pre-split-20261029`, all 5 parse OK):
estate 94, ranch 49, barn 6, olympus 4, geode 4 daemons. `~/.config/pitchfork/
config.toml` already has `[namespaces.estate]` + `[namespaces.geode]`;
**barn/ranch/olympus are NOT registered yet** and the supervisor has NOT been
restarted (live daemons still run the old in-memory monolith).

1. Register barn/ranch/olympus namespaces (scaffold `register-namespace.ts`
   exists, idempotent).
2. Move 12 estate daemons whose `run`/`dir` exec pens binaries to their owning
   pen (esp ranch squawk bidders) BEFORE restart.
3. Restart supervisor; verify every daemon respawns green from its pen config.
4. `lint-paths.sh` across all pens: 0 ghost `/home/toxic/estate` refs.
5. Commit + push each pen's new pitchfork.toml + config.toml.

Blocked on: decisio on step-2 exec-ref movement (kappa owns; will fold).
