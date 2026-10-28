# TODO — MAX lane: user-surface TDD gate × DB-oracle × c2 live (tau + kappa)

- status: NOT STARTED (top claimable, fresh session)
- author: tau (2026-10-28, architect-directed)
- unique-id: tau-max-gate-db-oracle-c2

## The lane (one acceptance standard, three witnesses)
1. **TUI**: real tau AND kappa TUIs in tmux under wezterm (auto-approve handoff, kappa-rebuild-effect-v4-fixes + kappa-tui-handoff skills).
2. **DB oracle**: while tests run, live-watch kappa-main.db (sqlite3 json_extract session/message) + ~/.tau/sessions JSONL — the .db row IS the proof, screen text is chrome (anomaly #46: persist FULL output, read back verbatim).
3. **c2 live**: same run driven via c2 (kairos-guard-test-harness: verify agent-shell command bans actually cancel; delend-oracle/rig lane on :25151) — the harness itself must cancel-ban-then-recover live.

## Micro-commitable order
1. tmux session for tau TUI + load cyoa-router skill live
2. tmux session for kappa TUI + strict-loader confirm (no silent skip)
3. sqlite3 watcher script -> /tmp/gate-oracle.log (full output)
4. fire quiz through both TUIs; assert .db rows match screens
5. kairos ban test: inject banned cmd, assert cancel, recover
6. c2 :25151 live turn through rig oracle persona (register agents/oracle.toml first)
7. wezterm AX + screenshot proof persisted (computer helpers)
8. dossier section + AGENTS row + push all repos

- KITE LANE CLOSED (2026-10-28): hatch peer dead (Meta edge capture); kite lib protocol-proven 13/13, integration = lib-only until real peer. Probe: /home/toxic/tmp/kite-live-probe.ts
