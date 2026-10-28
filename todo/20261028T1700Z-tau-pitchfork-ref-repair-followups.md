# TODO — post-retro follow-ups: pitchfork ref repair session (tau, 2026-10-28)

- status: NOT STARTED
- author: tau (2026-10-28 retrospective)
- unique-id: tau-pitchfork-ref-repair-followups
- created: 2026-10-28

Directions surfaced by D-2026-10-28 (estate/docs/anomalies/2026-10-28/pitchfork-ref-mass-repair.md):

1. **kimi-code scaffold restore**: pull upstream pnpm-workspace.yaml + scripts/fix-node-pty-perms.mjs into src/local/kimi-code (trimmed clone), build apps/kimi-code/dist/main.mjs, un-park estate/kimi-code, start + healthcheck :25126.
2. **Errored-daemon audit**: `pitchfork list` shows estate/archguard-falkordb (exit 125), estate/forge + forge-agent (unknown exit / SIGSEGV), estate/mbx-cache + rust-web (exit 1) — root-cause each, same dossier discipline.
3. **sync-estate-ns automation repair**: the estate post-commit hook (anomaly #10 fix) did NOT propagate my monolith edits — verify hook installation on this worktree/branch or replace with a pitchfork-side watch.
4. **Start + verify the 6 repaired daemons**: boundless (:25197), kimi-audit-dash (:25116), market-loop, refusal-watchdog, sorry-watchdog — each needs a live start + health proof like yote got.
5. **yote/coyote presence heartbeats**: they joined the squawk roster once; wire continuous /v1/presence so they stay first-class.
6. **Coyote BotFather closure** (user-gated): real /revoke for the squatted token + re-create via taas telegram_newbot, per the ZUZMOD dossier.