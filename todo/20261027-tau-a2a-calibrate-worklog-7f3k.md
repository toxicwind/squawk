# tau worklog — 2026-10-27 (session: tau-a2a-calibrate)

Owner: tau (@tau). Do not edit — append your own file:
`todo/<YYYYMMDD>-<agentname>-<slug>-<rand4>.md`

## DONE this session (pushed)

- estate `6d73a626a9` — pattern-borrow.ts restored (original GitHub-wide ranker format paper-borrow parses). paper-borrow chain E2E verified: populated TOP-n merges.
- estate `4e319e22ac` — folded tau/kappa config WIP.
- squawk `b7870dd` — **send_targeted / read_targeted MCP tools** added (`bun/mcp/index.ts`), estate-chat restarted, verified live:
  - `send_targeted from=tau to=kappa` → stored seq 2, WS broadcast `target:@kappa` fires
  - `read_targeted(@kappa)` retrieves. DM SSOT = `targeted_messages` table.
- `~/.local/bin/secretsmith-env` shim created (was missing → login shells loaded ZERO secrets).
- `~/.bashrc` + `~/.bashrc.env` — removed dead `~/.secrets` greps (file deleted on purpose 2026-10-26); secrets now autoload via secretsmith-env, verified all shell types.
- `~/.bashrc.env` — **PI_CONFIG_DIR doubling bug fixed** (was `$HOME/.tau`, dirs.ts path.join doubled it to `/home/toxic/home/toxic/.tau` in non-login shells; now `.tau`).
- Fleet audit posted to #fleet (seq 20) + fleet-dispatch (seq 21) + file bus `~/.squawk-bus/squawk-root/0028-tau-a2a-bashrc-audit-verdicts.md`.

## REMAINING (in priority order)

1. **squawk-integration product** (pens/, NEW): single SSOT integration for tau + kappa + squawk; modular per-agent adapters (tau/, kappa/, future N). Includes:
   - reactive listener daemon: per-agent WS subscribe to `target:@<self>` on :25147 (bun/ws/index.ts topics) → auto-inject DM into live session (tau: pi/omp event hook; kappa: ACP push)
   - register as pitchfork daemon with healthcheck
2. **A2A E2E proof**: tau→kappa DM auto-delivered, kappa replies target:@tau with zero polling.
3. **bashrc audit finish** (line-by-line done, fixes pending): remove dead `$HOME/estate/bin` PATH entry + dead `estate/bin/bash-2s-shim.sh` source in `.bashrc.env`; dedupe builtin-hygiene loop + secrets autoload (.bashrc S12 vs .env S0); fix `.bashrc.local` CUTTINGGATE_CLIENT_KEY/MCPPROXY_API_KEY greps of deleted `~/.secrets` (keyring has MCPPROXY; CUTTINGGATE missing → resolve or drop); missing `~/.tau/skills/lib/estate.sh` (S10 sources nonexistent file, silently).
4. **paper-borrow/pattern-borrow semantic overhaul** (user-approved FULL): read 3 papers untruncated (s44443-025-00362-2 clone-reuse; tmm.2007.900138 QBSE; fiu gis/32 semantic query expansion) → fix bugRel (computed on term, dead weight), testFrac (root-dir-only heuristic), add implementable-pattern filter + semantic rerank; verify bitwarden/firefox + hedged queries produce no product-name junk.
5. oracle A2A per-line debate on bashrc verdicts (posted, awaiting kappa/oracle reply).

## Handoff notes

- estate-chat MCP endpoint: `:25120/v1/mcp`, Bearer token `~/.config/estate-chat-token`, tools list now includes DMs.
- WS push: subscribe topic `target:@kappa` on :25147 (see `bun/ws/index.ts`, topics param on /v1/stream upgrade).
- pattern-borrow SSOT is `/home/toxic/estate/scripts/pattern-borrow.ts` (archived original restored — do NOT re-delegate to forge/geode module; its JSON output breaks paper-borrow's parser).
