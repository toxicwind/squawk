# freeinference global concurrency=2 queue — kafka-esque, enforced on ALL consumers (tau, kappa, qed, all pens)

- **Status:** NOT-STARTED
- **Found:** standing directive (architect), 2026-10-28; 67 freeinference 429s in 11 min
  (estate/docs/anomalies/2026-10-26/tau-report-*/REPORT.md)

## Current state (verified)

- kappa.jsonc: freeinference `maxConcurrency: 2` + `unlimitedRetryOn429` — per-process only.
- tau models.yml (mimetite-generated): glm-5.3-flash + deepseek-v4-flash `maxConcurrency: 1`,
  qwen3.6-35b UNSET — per-process only, inconsistent across products.
- rhodochrosite router (:25193): freeinference NOT a provider — direct freeinference calls
  bypass the router's concurrency gates entirely.
- delendai.config.json: `single-freeinference-owner` agent-control (partial).
- "no freeinference in swarm" tau rule = TEMPORARY until this lands.

## Fix direction

1. Pens-level SSOT: `pens/geode/products/mimetite` catalog gets freeinference
   `maxConcurrency: 2` on EVERY model (single var, everything dynamically references it).
2. Rhodochrosite adds a `freeinference` provider entry with a dedicated entrypoint +
   auto-fallback; its existing provider-concurrency gates then enforce 2 GLOBALLY for
   router-routed traffic.
3. Point kappa + tau + qed freeinference consumers at the router lane (or shared lease
   daemon if direct lanes must stay); timeouts 3000ms (user directive — 1000ms monkey
   patch underperforms).
4. 429 = shed-not-strike for freeinference (global lane, not per-model failure).

## Acceptance

- Two tau swarms + kappa + qed hitting freeinference simultaneously → zero 429s to callers,
  queue holds at 2, observable depth in rhodochrosite /status.
- "no freeinference in swarm" todo retired.
