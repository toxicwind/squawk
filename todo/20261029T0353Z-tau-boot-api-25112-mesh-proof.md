# Fleet todo: Boot API on :25112, prove /mesh/* + blackbird session resolve

## Origin
tau verify phase (verify lane), task "Boot API on :25112, prove /mesh/* + blackbird session resolve". Raised by the architect's board-sync ask ("write all todo separate verbose to squawk todo").

## What was done
- Estate mesh product `/home/toxic/pens/barn/products/estate-mesh` was repaired end-to-end:
  - `tsconfig.json`: added `allowImportingTsExtensions: true` (rule 5b: LSP diagnostics are contracts — never silence).
  - `src/mesh.ts`: `requirePort`/`urlFor` untangled from edit-tool collision garbage; `MESH_DEFAULT_PORTS` self-contained defaults added so mesh-only services (mesh-hub, brand, bench-radar) resolve even when ports.env lacks them; env wins → SSOT file → default → throw. `defaultPort()` helper wired into `requirePort`.
  - Catalog corrected to canonical `BORNITE_PORT` (legacy `HERD_PORT`/`LLAMA_SWAP_PORT` tokens removed — herd-rename.pairs was an identity stub; `llama-swap-to-bornite.pairs` exists but never ran).
  - 26-case TDD suite in `tests/mesh.test.ts` covering every feature + port edge cases + canonical-name regression. tsc clean; **26/26 pass**.
- GHAS copy synced (`packages/search-core/src/mesh.ts` identical to estate-mesh).
- `apps/api/src/lib/env.ts`: fixed root cause of the live :25112 `peers` 500 — `applyEnvFile` loaded `pens/estate/config/ports.env` inline without stripping inline comments, polluting `process.env.BORNITE_PORT` with `25100  # bornite = ...`; mesh's `loadPorts` respects existing env so the pollution survived. Now strips `\s+#.*$`. Dead `stripInlineComment` helper removed.
- Live API on :25112 restarted with the synced code; all surfaces verified live:
  - `GET /api/health` → `{"ok":true,...}`
  - `GET /mesh/features` → 20-feature registry
  - `GET /mesh/peers` → 13/13 peers, all canonical ports (bornite resolves via BORNITE_PORT default)
  - `GET /mesh/chain-health` → 207, 14/14 services probed, 5 live (honest degradation)
  - blackbird `GET /api/search?q=blackbird session` → real results with scores/highlights (antoniaci/blackbird, toxicwind/github-advanced-search-mcp AGENTS.md referencing `ghas_engine_info` / "Blackbird session / experimental rank")
- Both repos committed + pushed to main:
  - `toxicwind/github-search` → `546a360` (6 files: env.ts, mesh.ts, blackbird.ts, scripts x2, .gitignore — folds forward prior-session WIP per rule 1b)
  - `toxicwind/estate-mesh` → `68eb5b6` (mesh + tests)

## Acceptance
- tsc clean in estate-mesh; `bun test` 26/26 green.
- `:25112` /mesh/* all green + blackbird search resolves.

## Status
COMPLETE — archived here for the squawk index.
