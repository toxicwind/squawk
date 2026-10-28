# TODO — pens-ui master dashboard (MOST URGENT — architect directive 2026-10-27T20:1xZ)

- author: tau (session 2026-10-27, awrawr-pc)
- status: DONE (by daemon, 2026-10-28T12:41:24.653Z)
- unique-id: TAU-20261027-pens-ui-master-dashboard

## Why most urgent

The estate has FOUR overlapping dashboard/UI surfaces and no single master:
- ranch-ui :25218 (bun, estate/stack/services/ranch-ui.ts) — proxies delendai-control-plane
  SPA (React 19, pens/ranch/range/apps/delendai-control-plane, vite :25156) + bornite API
- range-ui.tmp/ui — Svelte 5 tabbed surfaces app (52-entry iframe registry,
  src/lib/surfaces.ts; ports SSOT via config/ports.env → generated ports.ts)
- squawk campfire :25121 + fleet-ui :25136 — chat/fleet surfaces
- forge web :25164/:25165 — Next.js 16 (REAPI cache UI + docs)

Architect decision: build **pens-ui** at `pens/products/pens-ui` as THE master
integration — do NOT monkey-merge tab registries into each surface. One app,
tabs iframe the per-product UIs (surfaces.ts pattern generalizes).

## Plan

1. Scaffold pens/products/pens-ui (Svelte 5 + vite, matching range-ui.tmp/ui
   conventions: surfaces.ts registry, loopback() from ports.env SSOT).
2. Port surfaces.ts registry; add MISSING tabs: forge-web :25164, forge-docs
   :25165, nativelink :25155 status, skopos (hot-reload/debug per directive).
3. Single pitchfork daemon `pens-ui` (port from config/ports.env; :25218
   ranch-ui becomes a proxy/shim to pens-ui or retires — architect's call).
4. Hot reload + auto refresh + debug mode ON for all embedded UI surfaces.
5. Verify every tab loads its live origin; commit + push.

## Stop-point context (this session, before this todo)

- forge-nl-lib landed: pens/ranch/forge/lib/forge-nl-lib.ts (polygot cache
  wrapper: bazel/cargo/bun/python/go/bash/perl + NL_LANGUAGE_SERVERS map).
  bazel+http probes verified live (grpcUp true after Promise.race fix).
  NOT yet wired into estate-wide buildscripts; not committed/pushed yet.
- tsgo purged from code-insiders (typescript-go#2239 leak froze Wayland);
  tsserver restored. marketplace reinstall fails signature-verify — wait for
  7.1-based extension tag before re-enabling.
- flicker-server/agent SIGSEGV crash-loop every ~10s still unpatched (494
  coredumps/24h). Cheap fix candidate: pitchfork retry=false or exec-lane fix.
- wezterm 13:43:05 segfault was collateral of tsgo memory thrash; no action.

---

## APPENDED 2026-10-27T20:1xZ — kappa model-switching gaps (tau findings)

- **status: NOT STARTED — bundled with pens-ui arc (same surface)**
- Finding: `kappa.json` `"model"` key is INVALID (startup warning: "Unrecognized key"); `provider.defaultModel()` falls back to `~/.local/state/kappa/model.json` `recent[0]`.
- Finding: `KappacodeModelState.Patch` only supports `favorite` — **no API/agent path to change the active model**; only TUI picker mutates recents.
- TODO A: fix kappa config schema — either honor `"model"` in kappa.json or update the mimetite-generated config template to stop writing it.
- TODO B: add `model.set` to `KappacodeModelState.Patch` + server route (`POST /v1/model/recent`-style) + MCP tool `change_model` so agents (not just humans in TUI) can switch kappa's model.
- Verified working state: kappa tmux session `kappa-interactive` pinned via model.json recents; default code agent still qwen3.6-35b until picker used once or TODO B lands.

## Done
- marked-by: daemon
- marked-at: 2026-10-28T12:41:24.653Z
