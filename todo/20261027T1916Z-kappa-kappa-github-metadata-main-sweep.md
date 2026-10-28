# TODO — github metadata + MAIN-MAIN sweep (kappa fleet)

- agent: kappa (session 2026-10-27T19:16Z, box awrawr-pc)
- created: 2026-10-27T19:16Z
- status: DONE (marked by daemon)
- unique-id: KAPPA-20261027T1916Z-github-metadata-main-sweep

## Jobs

1. Rename `toxicwind/kilo-cli` -> `toxicwind/kappa-cli` (gh repo rename; GitHub
   redirects old name). Then fix remotes: kappa monorepo `.gitmodules` (kappa-cli
   url -> https://github.com/toxicwind/kappa-cli.git) and the local
   `pens/olympus/products/kappa/kappa-cli` origin URL. Update root README table.
2. Set descriptions (drop estate jargon) on all 4 repos:
   - kappa (PRIVATE->consider PUBLIC; flagship): "Kappa (κ) monorepo — open source
     AI coding agent: CLI/TUI, VS Code, JetBrains; browser-fingerprint transport
     - flail gate"
   - kappa-code (PUBLIC, currently says "Estate-forked"): "The kappa engine —
     open source AI coding agent runtime (fork of Kilo Code/opencode)"
   - kappa-ble (currently EMPTY desc): "First-class kappa x ble.sh integration
     (bash line editor): env fix, prompt unit, Ctrl-x k"
   - kappa-cli: "Kappa CLI tooling mirror (pinned; dev happens in kappa-code)"
3. Add topics to all 4: ai-agent, cli, typescript, bun, coding-agent, llm (+ fork,
   ble-sh for kappa-ble).
4. Fix `.gitmodules` kappa-ble url (/home/toxic/... local path ->
   https://github.com/toxicwind/kappa-ble.git), commit root repo.
5. PR/stash/branch hygiene status (AUDITED 2026-10-27, CLEAN): no open PRs, no
   stray branches, no stashes on kappa/kappa-code/kappa-ble; kappa-code PR
   history: 14 merged PRs, #17 CLOSED superseded. Only remaining: verify kilo-cli
   PR surface after rename.

## Verification

- gh repo view toxicwind/{kappa,kappa-code,kappa-ble,kappa-cli} shows desc+topics
- git ls-remote on all 4 -> main is default and pushed
