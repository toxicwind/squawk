# TODO — EMERGENT ENDLESS TASKING (goal-mode maximal board, verbose)

- author: tau (session 2026-10-28, awrawr-pc)
- status: IN PROGRESS
- unique-id: TAU-20261028-goal-endless-tasking

## Phase A — endless-village (the goal core)

- [x] **Rig census** — 7 prenamed rigs joined (skopos 👁 / muse 🎐 / keryx 📯 /
      kryptos 🗝 / kairos ⏱ / ergane 🪡 / hestia 🔥), vein keys minted
      (`rig-<name>` → secretsmith keyring + sha256 into rhodochrosite store),
      rhodochrosite restarted. Evidence: census output, agent ids
      133ab66c/7ff21482/10f9f075/212452d6/b5e58613/ea1e43c5/f30275ae.
- [ ] **Village-clock daemon** — `pens/ranch/geode-rig/village-clock.ts`:
      finish resolveKeys() (secretsmith env regex — replace stale execTrim),
      bun parse check, pitchfork daemon `village-clock`, start, observe the
      first murmuring wave in fleet room.
- [ ] **IRC awareness** — scan `ports.env` + `ss -ltnp` for an IRC surface
      (6667/6697/ergo/thresher-irc bridge); wire rig presence to whatever
      exists; if none, declare IRC a MISSING PREREQUISITE in the board, do
      not invent one silently.
- [ ] **Agent/subagent/model awareness SSOT** — `rig-manifest.json` extended:
      rig → place → lane → model → key label → cadence; published to
      ergasterion docs + squawk; every rig's system.md references it.

## Phase B — model sovereignty (the "Each" directive)

- [ ] **Per-model standalone configurability** — every model on every geode
      router/provider: parse `~/.rhodochrosite-data/config.json` providers.*,
      emit per-model config surfaces through mimetite build (tau models.yml +
      kappa-models.json `provider.model` entries), each with its own
      override-able knobs (temperature, max_tokens, headers, effort).
- [ ] **Provider-wide configurability** — maxConcurrency / UA / retries /
      auth_headers as ProviderDef fields in mimetite `data.ts` (config not
      code), regen, live-probe ≥3 models, record exits.
- [ ] **Clean-arch enforcement** — purge nested ranch snapshots from estate
      (Anomaly #7 class); pens projection invariant (sync-scripts only
      writers); ranch `git status --porcelain` empty check.
- [ ] **Doctrine merge into rigs** — append to all 9 rig system.md: the
      clean-arch constitution, no-human-gate (Asking User is a bug; Oracle
      :25151 for approvals), Unreliable Narrator Doctrine (verify via
      /proc/ss/curl, never trust error strings), furry-persona lane anchoring.

## Phase C — smithy debt (carried threads)

- [ ] **Bun canary real upgrade** — `bun upgrade` to 1.4.4-canary.20261027.1,
      verify `Bun.version`, rebuild affected products.
- [ ] **Codemod** — 334 `fs.writeFile` → `Bun.write` via mass-perl.pl;
      agent-worktree.tool.ts cast ladders.
- [ ] **Gemini-mcp own entrypoint** — GEMINI_MCP_PORT=25227 in ports.env,
      both pitchfork monoliths, tailscale serve route, X-MCP-Token gate.
- [ ] **Hephaistos wields geode** — gem surfaces as first-class hephaistos
      plugins (rhodochrosite/bornite/azurite toolheads).

## Phase D — phone fleet

- [ ] **Firefox CDP** — regenerate device code (2B94-0CA8 expired), drive the
      phone authorize (freeform window, never steal focus), enable the
      remote-debugging toggle, `adb forward` + verify.
- [ ] **EAP billing** — prepay funds or free-tier toggle at ai.studio/projects
      (USER-BLOCKED — only the architect can).

## Phase E — sprite forge

- [ ] **Kenney submodule** — eidolon/assets/kenney (puny-characters +
      puny-world, CC0).
- [ ] **AI-gen citizens** — geode/hephaistos/tau/kappa via eidolon NVIDIA
      lane (nemotron-flux first, gemini-3.1-flash-image fallback), seeds
      deterministic per rig.
- [ ] **Farm tab** — pens-ui master dashboard: Kenney tilemap, daemons as lit
      buildings, squawk speech bubbles, day/night from poll cadence,
      seasons = deploy cycles.
- [ ] **Blackbird persist** — GITHUB_SESSIONS config + only-search-surface
      doctrine line in estate AGENTS.md.

## Recursion law

Every checkbox, when opened, spawns sub-todos in this file (or a linked
`YYYYMMDDThhmmZ-<agent>-<slug>.md`); closes only with commit-hash or probe
evidence. The board never shrinks silently: shrinking IS a todo.
