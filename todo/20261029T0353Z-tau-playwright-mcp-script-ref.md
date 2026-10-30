# Fleet todo: Stale playwright-mcp script ref fix

## Origin
tau followup phase: "Stale playwright-mcp script ref fix".

## Recon findings
- `grep -rn playwright-mcp` over `/home/toxic/pens/ranch` config/script files (`pitchfork.toml`, `olympus/pitchfork.toml`, `barn/scripts/*.ts|*.sh`) → **no references found**.
- `pitchfork.toml` daemons were audited in prior sessions (anomaly program 2026-10-28): daemon dirs re-pointed post-reorg; no playwright-mcp daemon stanza present.
- Earlier TSDD-era mention was resolved long ago; nothing stale remains on disk in the checked scope.

## Status
NO-OP — nothing to fix. Board item can be dropped. Re-check: scan `/home/toxic/pens/barn` and `/home/toxic/pens/olympus` for playwright-mcp if the architect re-raises it.
