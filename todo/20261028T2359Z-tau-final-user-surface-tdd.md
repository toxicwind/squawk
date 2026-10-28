# TODO — FINAL acceptance gate: user-surface TDD via real kappa (wezterm+tmux)

- status: NOT STARTED
- author: tau 2026-10-28
- unique-id: tau-final-user-surface-tdd

Doctrine (architect): integrations are DONE only when proven on the REAL user surfaces —
not bun test, not curl. Run the kappa-tui-handoff pattern:

1. tmux new-session: kappa headless TUI with auto-approve
2. Inside real kappa: load cyoa-router skill (tau-side resolvable + kappa strict-loader OK)
3. Real quiz run end-to-end inside kappa TUI (12 questions -> weighted route)
4. Provenance gate live call inside kappa (unreliable-narrator filter on a real search)
5. Screenshot/AX proof from wezterm surface; persist to estate snapshots
6. Then (and only then) mark cyoa-router "final-TDD: user-verified" in AGENTS/KB


## AMENDED (architect): tau included
Same gate for TAU — real tau TUI in tmux under wezterm (auto-approve handoff), loading cyoa-router/provenance live, AX/screenshot proof persisted. BOTH tau AND kappa must pass user-surface proof before any of this arc counts as shipped.
