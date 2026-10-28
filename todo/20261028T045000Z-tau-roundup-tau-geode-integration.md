# TODO — roundup: tau + geode integrated and used (freeinference → measured-NVIDIA swap)

- status: NOT STARTED
- author: tau (session 2026-10-28, awrawr-pc)
- created: 2026-10-28
- unique-id: tau-roundup-tau-geode-integration

## The ask (architect, verbatim energy)
"roundup needs to be tau and geode integrated and used" + "was roundup renamed to a geode use bun for eval?" + "something of ours is using freeinference when it should be set to one of the newer fastest nvidia models — make new todo where maximally forward."

## Audit findings (2026-10-28, ground truth)
- **roundup** = standalone ranch repo (`pens/ranch/roundup`, Guidellm fork) — NOT inside geode; its git origin is the ranch amalgam (no separate origin). It ranks all local+cloud models on quality-descending / p50-ascending (cost ignored).
- **rename-roundup** = the fork-rebrand engine (mass-perl/rename.ts) — red herring, NOT a rename of roundup.
- **geode products** = azurite, bornite, chalcopyrite, mimetite, rhodochrosite — no eval/roundup product today.
- roundup tooling: `mise tasks.bench` (roundup-bench.sh, instruction_following), `bench-v3` (capability probing), `estate-sweep` (**already Bun**: `bun ./sweeps/roundup-estate-sweep.ts`).
- **tau is split-brain**: role lanes already point at `nvidia/nemotron-*` (config.yml:259-272 advisor/commit/judge/memory/plan/slow/task/tiny/verification), BUT defaultModel=freeinference/qwen3.6-35b (:448), model lists still freeinference (:372-374), router disabled/enabled:false (lastNonRouterModel=freeinference/qwen3.6-35b), Tauvisor=freeinference/deepseek-v4-flash:low.
- NVIDIA catalog has the goods: nemotron-3.5-super-vl, nemotron-3-super-free, nemotron-3-ultra-free, nemotron-3-nano-30b-a3b, nemotron-3.5-lightning-free, mistral-nemotron-Nano-8B etc. rhodochrosite health=ok (:25193) but /v1/models needs proxy auth key.

## Mission (maximally forward)
1. **Make roundup a geode product** — move/register as `pens/geode/products/roundup` (metá peer, manifest, pens.yaml); keep its Bun estate-sweep as the primary eval runner; docs.
2. **Prove the faster-NVIDIA claim with roundup, not vibes** — run estate-sweep (bun) covering: freeinference/deepseek-v4-flash, freeinference/qwen3.6-35b, freeinference/glm-5.3-flash, minimax-m3.1-flash vs nvidia/nemotron-3.5-lighning-free, nemotron-3.5-super-vl, nemotron-3-super-free, nemotron-3-ultra-free + rhodochrosite-proxied NIM lane. Emit the ranking JSON/CSV to roundup/results.
3. **Tau consumes roundup rankings** — wire the winner into: defaultModel, model lists (:372-374), Tauvisor model, and re-enable the router with the NVIDIA-fast lane as primary. NEW default per data, not guesswork.
4. **Geode/mimetite SSOT refresh** — regenerate models.yml/catalog from the measured ranking (mimetite build), so the whole estate inherits one measured truth.
5. **Roundup used continuously** — make bench-v3 a pitchfork cron daemon (or wagon wheel via estate-todo) so the ranking refreshes and the router self-updates: measured, forward, no stagnation.
6. **Docs + changelogs** — roundup README integration map, geode PLAN entry, tau config provenance note, anomaly-dossier style entry if a ranking surprises.

## Success gate
- roundup listed under geode products + metá manifest.
- estate-sweep run with both freeinference + NVIDIA lanes, results committed to roundup/results.
- tau defaultModel + Tauvisor + router point at the roundup-measured winner (expected: an NVIDIA/NIM lane), freeinference demoted to fallback, with the ranking JSON as the cited evidence.
- bench-v3 scheduled (cron) so the ranking stays live.