# TODO — fork imagine-server -> olympus/products/eidolon (real image gen)

- agent: kappa (session 2026-10-27T19:16Z, box awrawr-pc)
- created: 2026-10-27T19:16Z
- status: NOT STARTED (research DONE, decision MADE)
- unique-id: KAPPA-20261027T1916Z-eidolon-imagegen-fork

## Decision (from completed research, ranked comparison)

WINNER: https://github.com/Amery2010/imagine-server (MIT, TS, 120 stars, active)

- 8 providers (HF, Gitee AI, ModelScope, A4F, ModelsLab, Gemini, Grok, OpenAI)
- clean IProvider/BaseProvider plugin architecture: src/providers/base.ts + registry.ts
- Hono + unstorage + Zod; deploys on Cloudflare Workers/Vercel/Node (Bun-friendly)
  Runner-up: WuMingDao/zenith-image-generator (225 stars, fresher, but 4 providers,
  React-coupled). Evidence: raw.githubusercontent.com/Amery2010/imagine-server/main/src/providers/registry.ts

## Jobs

1. Fork upstream into toxicwind/eidolon (GitHub fork or fresh clone + provenance
   README crediting Amery2010/imagine-server), clone to
   pens/olympus/products/eidolon. Greek name fits olympus lineage (eidolon =
   image/phantom).
2. Register in olympus + barn/estate-ops bin manifest if it ships a bin.
3. Add providers (one file + registry entry each, per their plugin guide):
   Pollinations (flux, NO key — make it the default provider), Cloudflare Workers
   AI (FLUX.2 Klein free tier), fal.ai (100 free credits), NVIDIA NIM free
   text-to-image endpoints (build.nvidia.com category: Image Generation).
4. Replace Chinese-language docs with English (keep upstream provenance section).
5. Provenance-first: verify each free endpoint with a live probe (HTTP status +
   bytes + latency) before trusting catalogs (DECLARED != OBSERVED).
6. Green-blue: keep prior runnable state (imagine-server as-is) until the new
   providers healthcheck; pitchfork daemon + healthck when stood up.
7. Surface in kappa READMEs: hero image is deterministic SVG->WebP today
   (docs/hero.webp in kappa + kappa-code); optionally wire eidolon-generated art
   later. Do NOT block on it.

## Verification

- bun test in eidolon passes; live probe of each new provider returns 200 + image bytes
- pens/olympus/products/eidolon exists, clean git status, pushed to origin
