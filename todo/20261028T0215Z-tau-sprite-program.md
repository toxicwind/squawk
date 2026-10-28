# TODO — sprite program: living AI-Harvest-Moon citizens (recursive)

- author: tau (session 2026-10-28, awrawr-pc)
- status: IN PROGRESS (fork + provider DONE; tiles + dashboard + loop wiring next)
- unique-id: TAU-20261028-sprite-program

## The shape (don't break the wheel — fork + submodule, never rebuild)

1. [x] **eidolon fork** — toxicwind/eidolon (Amery2010/imagine-server, MIT),
   cloned `pens/ergasterion/eidolon`, NVIDIA NIM provider forged
   (SDXL + Flux, rhodochrosite-vein-first, commit `d25a557`).
2. [ ] **Kenney submodule** — `pens/ergasterion/eidolon/assets/kenney` ←
   git submodule of kenney/puny-characters + puny-world (CC0 tiles/fallbacks).
3. [ ] **AI-gen the citizens** — one sprite per rig via eidolon:
   geode (crystalline palette), hephaistos (soot+gold), tau, kappa.
   Prompt DSL in `sprites/prompts.md`; deterministic seeds per rig;
   NVIDIA lane FIRST (nemotron-flux), gemini-3.1-flash-image fallback.
4. [ ] **pens-ui master dashboard — the Farm tab** (hooks the MOST-URGENT
   pens-ui todo): Kenney tilemap, pens/ tree → world map, daemons = buildings
   (window lights = health), rig villagers idle-walk, squawk messages =
   speech bubbles, day/night = poll cadence, seasons = deploy cycles,
   rain = retry storms.
5. [ ] **Rig loop runner** — geode-poll.ts (already at `pens/ranch/geode-rig/`)
   becomes her actual agent loop: system.md persona → nemotron turn → facet
   to squawk → JSONL ledger. Pitchfork daemon `geode-poll`. Then clone the
   pattern for hephaistos (ergasterion) and the barn rig when claimed.
6. [ ] **Sprite mutation doctrine** — CC0/Kenney + AI-gen only; Sprout Lands
   and other license-encumbered packs are FORBIDDEN for mutation.

## Recursion law

Each numbered item spawns its own sub-todos when opened; close with evidence
(commit hash or probe output) — never claims.
