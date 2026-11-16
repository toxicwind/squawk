# TODO — NGC activation-plane recon: integrate into mimetite + wire fi-flash (deepseek-v4-flash) route

- author: hermes (depth-bench 2026-11-10, deepseek-v4-flash via freeinference)
- created: 2026-11-10T11:19Z
- status: DONE
- unique-id: HERMES-20261110T1119Z-ngc-activation-plane-mimetite

## Problem (target surface)

Third orthogonal NGC recon, distinct from the model plane (docs/anomalies-2026-11-10.md)
and the NVCF function plane (research/nvcf-vs-integrate.md). Scope: the activation /
entitlement plane — `org.ngc.nvidia.com/activate` and the admin/role schema behind it.
Live-probed unauthenticated; no serial/token/promo ever POSTed (gate is server-side).

## What was integrated (all DONE)

1. **Research doc** `geode/products/mimetite/research/ngc-activation-plane.md` —
   the 30-probe matrix, OpenAPI v3.249.17 schema, 370-role catalog, and the three
   confirmable anomalies (public-surface asymmetry, no HTTP API for activation,
   subscription-is-an-approval-workflow).
2. **`fi-flash` alias** → `deepseek-v4-flash` (freeinference) added to
   `scripts/build-hermes.ts` FI_PICKS — makes the current-running model a
   first-class selectable route (`fi-free`/`fi-coding`/`fi-flash`).
3. **Bench seed** `fi-flash` added to hermes mimetite plugin cold-start seeds.
4. **Rebuild** → regenerated all Pens artifacts (providers.json/.go/.rs,
   tau-models.yml, kappa, rhodochrosite + flock-proxy .rs). Build exit 0.
5. **Conformance** run. Result: 11 routes in drift — ALL pre-existing contract drift
   (cerebras 403, deepinfra 404, qianfan 429, google-antigravity 404,
   vercel-gateway/freeinference 401/429 with keys). NONE traceable to my edits
   (fi-flash is additive; no provider contract touched).

## Confirmable anomalies (evidence in research/ngc-activation-plane.md)

- A1. Public-surface asymmetry: `/activate`, `/roles`, `/v3/api-docs`, `/.data`
  answer **200 with zero auth**; everything adjacent 401.
- A2. No HTTP API for activation: 77-path OpenAPI v3.249.17 greps 0× serial, 0× promo;
  only entitlement reads are admin-only and declare HTTP 402.
- A3. Subscription is an approval workflow: three `*_SUBSCRIPTION_REQUEST_APPROVER`
  roles in the public 370-role catalog; zero roles govern "promo".

## Definition of done

- [x] research article written, artifact-linked, sha256-anchored
- [x] `fi-flash` route selectable (alias + bench seed + custom_providers/models)
- [x] build regenerates all Pens artifacts, exit 0
- [x] conformance re-run; drift isolated to pre-existing, none from this change
- [ ] (open in real world, not this ticket) submit a serial through the RSC action
      under an **authenticated org-owner** session to observe the "on hold" state
      machine — requires a live owner session; not done here (we POST no fakes)