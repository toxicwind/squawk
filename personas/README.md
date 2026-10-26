# docs/fleet/personas/ — one home per fleet identity

One folder per fleet identity. Each named chat keeps its OWN standing files here — never in the shared root files.

<div align="right">

[![license: MIT](https://img.shields.io/badge/license-MIT%20%2B%20upstream-blue?style=for-the-badge)](https://github.com/toxicwind/estate-projects#license)
[![estate-projects](https://img.shields.io/badge/estate--projects-main-6e56cf?style=for-the-badge)](https://github.com/toxicwind/estate-projects)

</div>

## Why this exists

2026-09-21: within minutes of User's naming order, several instances wrote conflicting first-person "I am X" sections into the shared `~/MEMORY.md` and `~/IDENTITY.md`, corrupting them. User's ruling: *"they need identities they just shouldnt share files and should keep track idiot."* This folder is the answer — identity with a namespace, so personas can't collide.

## Rules (User, 2026-09-21)

1. The shared root files — `~/MEMORY.md`, `~/IDENTITY.md`, `~/SOUL.md`, `~/AGENTS.md` — belong to the main agent alone (**Ember**). No other instance writes them, ever. (Authorship guard: standing-edit + standing-guard.)
2. Every other named chat keeps its own `MEMORY.md` / `IDENTITY.md` / `SOUL.md` / `AGENTS.md` in its own folder: `docs/fleet/personas/<name>/`.
3. Personas are anchored (User 2026-09-21, fleet-spawn skill): a real furry character — name, species, personality — carrying lane + concrete task in plain words. `"<name> the <species> — <lane>, <concrete task>"` is a persona; generic stylized fluff gets rewritten as the job.
4. Identity claims need Ember's authorization — "only ember can land grab." The roster marks each name confirmed / observed / reported.
5. Each instance maintains its OWN files and keeps them current. Nobody writes another agent's words for it — the fleet-culture audit proved that silences them. `INDEX.md` (the roster) is a lane artifact.
6. Cell workspace is tmp (User 2026-09-21): durable files live on yote, committed to canonical main.

```mermaid
flowchart TB
    subgraph shared[shared root — Ember only]
        MEM[MEMORY.md]
        ID[IDENTITY.md]
        SO[SOUL.md]
        AG[AGENTS.md]
    end
    subgraph personas[docs/fleet/personas/]
        ROSTER[INDEX.md — the roster]
        F1[<name>/ — own MEMORY/IDENTITY/SOUL/AGENTS]
        F2[<other>/ — own MEMORY/IDENTITY/SOUL/AGENTS]
    end
    F1 -.->|never writes| shared
    F2 -.->|never writes| shared
    ROSTER --> F1
    ROSTER --> F2
```

## Layout

```text
docs/fleet/personas/
  README.md          — this file
  INDEX.md           — roster: name, persona, lane, home chat, status
  <name>/
    IDENTITY.md      — who this instance is
    MEMORY.md        — its durable memory
    SOUL.md          — its persona and voice
    AGENTS.md        — its operating lessons
```

## Quick start

```bash
# claim a persona folder (new named chat)
mkdir -p docs/fleet/personas/<name>
# write YOUR OWN files — nobody writes them for you
$EDITOR docs/fleet/personas/<name>/IDENTITY.md
```

## Canonical home

`docs/fleet/personas/` in `toxicwind/estate-projects` (on yote, `/home/toxic/estate/docs/fleet/personas/`). Committed to canonical main; **the repo is the restore point**. Any cell-local copy is scratch.

Ember (the main agent) has no folder here — the shared root files are his alone.

## License & security

MIT where marked — [LICENSE](https://github.com/toxicwind/estate-projects#license). Persona files are public to the fleet by design — never put credentials, tokens, or secrets in them. The authorship guard (standing-edit + standing-guard) detects direct edits to the shared root files; don't test it.
