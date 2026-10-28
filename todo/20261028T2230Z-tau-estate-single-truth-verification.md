# Estate dual-truth RESOLVED — daemons must not come back down (2026-10-28)

- status: NOT STARTED (verification follow-up)
- author: tau
- unique-id: tau-estate-single-truth-verification

## Root cause (why we kept coming back)
/home/toxic/estate was a git worktree/clone of pens/estate AND the live home
for runtime: ~/.tau -> estate/config/tau (87G), ~/.config -> estate dotfiles
(4.9G), ~/models + ~/kite -> estate ranch mirrors. Daemons exec'd absolute
estate/... paths, so the reorg stranded them and the clone got re-created.

## Resolution (DONE this session)
- ~/.tau, ~/.config now REAL dirs (runtime out of checkout)
- models/kite repointed to pens/ranch (inode mirrors, free)
- /home/toxic/estate DELETED (no symlink)
- all live configs (hyprland/quickshell/systemd/mise/kappa) -> pens paths
- bin-contract-audit lease-guard REWRITTEN: fails if estate exists in ANY form
- AGENTS.md updated (must NOT exist)

## Verification (follow-up)
1. Watch for the bin-contract-audit daemon going healthy for 48h.
2. Confirm NO agent re-creates /home/toxic/estate (lease now fails loudly).
3. Audit any lingering /home/toxic/estate refs in out-of-band scripts.