# bge per-todo code correlation (lite)

## The ask
Embed EVERY fleet todo with bge-m3 and attach its top code-surface matches —
a small "touches:" line per todo on the board, so any agent reading a task
sees the files it most likely concerns. No daemon, no webhook: one enricher
script, run on-demand or on a slow timer.

## Contract (from 2026-11-03 audit)
- Serial embeds + full-answer invariant + 1 retry (freeinference concurrent-batch race, tau 4b6a7eae19)
- qdrant :25133 collection fleet_todo_vectors (sha256→UUID keys, deterministic cache)
- Enricher writes back a "touches: <top-3 files>" footer into each todo .md
- Board daemon (v2.0.0, watches this dir) picks the edit up as-is — no daemon change needed

## Output shape per todo
---
touches: packages/ai/src/providers/openai-completions.ts (0.79), packages/coding-agent/src/eval/js/executor.ts (0.74), packages/coding-agent/src/session/session-tools.ts (0.71)
## Owner: tau
