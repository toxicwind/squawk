# kappa MCP filesystem server: search_files times out (MCP error -32001), brittle npx cache path

- **Status:** NOT-STARTED
- **Claimed by:** nobody
- **Found:** 2026-10-28T19:42Z, live kappa session (twice in one hour)

## Symptom

`filesystem_search_files` (MCP server "filesystem") fails with:

```
MCP error -32001: Request timed out
```

Observed twice on `/home/toxic` recursive searches in the same session.

## Config evidence (`~/.config/kappa/kappa.jsonc`)

- MCP filesystem server is pinned to an npx cache hash path:
  `/home/toxic/.npm/_npx/a3241bba59c344f5/...` — if npm evicts/rebuilds the cache the
  server either dies (silent tool loss) or cold-starts slow.
- `startup: 30` (s) timeout on MCP; a cold npx resolution can eat most of it.

## Fix direction

1. Replace the npx-cache pin with a durable install (`bun add -g` or a vendored checkout
   under pens) and point MCP at the real path — bin-contract style, no cache roulette.
2. Investigate why `search_files` specifically hangs on large recursive trees (the server's
   glob walk has no bounded depth/time) — patch upstream or wrap with a bounded timeout at
   the kappa MCP client so a hung tool call fails fast instead of blocking the turn.

## Acceptance

- `filesystem_search_files` on /home/toxic returns (or fails bounded) in < 5 s.
- No npx cache path in kappa.jsonc; survives `npm cache clean`.
