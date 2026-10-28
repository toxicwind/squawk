# TODO — freeinference queue contention: dedicated entrypoint + auto fallback (geode/rhodo)

- author: kappa (ses_e815d2c0fffeqbvL2TJ11k9uX9, glm-5.3-flash)
- created: 2026-10-27T19:39Z
- status: DONE (marked by daemon)
- unique-id: KAPPA-20261027T1939Z-freeinference-queue-entrypoint-auto-fallback

## Problem (verified pattern)

kappa and tau (and any other fleet agent) FIGHT for the freeinference queue.
FreeInference (`freeinference.org/v1`) is the primary fast inference lane and its
queue is single-lane (estate doctrine: advertised limit 2, de facto 1 —
OBSERVER EFFECT / SINGLE LANE, anomaly #4). Multiple agents hammering it at once
=> 429 storms / serialization that LOOK like model failures but are queue
contention. This is an ORCHESTRATION defect, not a provider defect.

## Architect directive (what was asked, in order)

1. **Dedicated freeinference entrypoint in geode AND rhodo** (rhodochrosite —
   the UA-forwarding proxy, anomaly #14): a first-class endpoint for
   freeinference models so agents route through ONE queue-aware front door
   instead of raw-hitting freeinference.org in parallel. Rhodo is the right
   seam (it already owns UA/Cloudflare handling); geode hosts the product-side
   entry. Queue-awareness: single lease/scheduler across ALL agents (like the
   estate LeaseScheduler pattern: one lease per key, agents queue, probes
   serialize behind workers).
2. **An `auto` model** that auto-falls-back across ALL available freeinference
   models (glm-5.3-flash, qwen3.6-35b, deepseek-v4-flash, minimax-m3) —
   per the 2026-10-27 architect strike rule: FREE > FAST >
   instruction-following; strike/quarantine is per (provider, model). `auto`
   = walk the model list by that priority, skipping struck models (record
   model strikes already exists in the router — reuse, don't duplicate).
3. **An `auto-sse` variant with roost** — sanity-check flag: **roost is
   RETIRED** (estate naming doctrine: "super-ralph and roost are retired —
   never reference them"). Interpretation of intent: an SSE-streaming auto
   route (streaming token passthrough with automatic model fallback mid-or-at
   session start) wired through whatever succeeded roost in the current mesh
   (corral / the 25xxx fleet lanes). Whoever picks this up: confirm with the
   architect whether they literally want roost revived or meant its
   replacement — DO NOT resurrect a retired product without an explicit order.

## Definition of done

- [ ] freeinference entrypoint live behind rhodo (UA-forwarding honored,
      queue-lease shared across agents, healthcheck via pitchfork daemon)
- [ ] geode-side product entry registered (manifest + bin if it ships a bin)
- [ ] `auto` model: priority walk FREE > FAST > instruction-following with
      per-model strike skip; contract-tested (DECLARED != OBSERVED — probe
      each fallback leg before trusting the catalog)
- [ ] `auto-sse`: streaming + fallback, real SSE frames end-to-end
- [ ] One queue, zero agents raw-hitting freeinference.org
- [ ] Naming conflict on "roost" resolved with the architect
