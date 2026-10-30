# Fleet todo: Recon /home/toxic/estate resurrection source (lease violation)

## Origin
tau followup phase: "Recon /home/toxic/estate resurrection source (lease violation)".

## Background
AGENTS.md bin contract (lease, 2026-10-28): `/home/toxic/estate` must NOT exist in any form (no symlink, no dir, no file). SSOT is `/home/toxic/pens/estate`. On recon it was found existing as a real dir containing only stale `.state/` JSONs (`live-models.json`, `provider-catalog.json`, `provider-catalog.live.json`) plus `var/` and `agents/` — leftover ghost from pre-reorg. Nothing in pitchfork.toml / estate-ops references it (checked via fs read of candidates).

## Action taken
- `rm -rf /home/toxic/estate` — ghost removed; lease restored (no path now exists).

## Remaining (open)
- Identify what process/script recreates `/home/toxic/estate` (suspected: pitchfork.toml ghost entries, a daemon ready_cmd, or a stale grafana provisioning path) so it can't resurrect. Check supervisor logs / daemons referencing `estate/` absolute paths.
- If recreated by anything, fix at root (per rule 2: never remove/disable a daemon without explicit order — fix the reference instead).

## Status
IN PROGRESS — ghost removed; respawn source not yet identified.
