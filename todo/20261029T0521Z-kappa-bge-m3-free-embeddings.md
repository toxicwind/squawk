# TODO — bge-m3 free embeddings: register + route + wire into all indexers

- status: NOT-STARTED
- author: kappa (2026-10-29)
- unique-id: kappa-bge-m3-free-embeddings
- priority: high
- collab: OPEN (welcome tau, geode rigs, anyone touching retrieval)

Recon done (2026-10-29): FreeInference serves **bge-m3** (BGE-M3, 8K ctx,
embeddings-only, **$0/1M**, Pro-key on pro plan) via OpenAI-compatible
`POST /v1/embeddings`. Docs: `doc.freeinference.org/models.html` §Embedding
Model. The estate's routers/catalog DELIBERATELY exclude it
(`mimetite/src/data.ts:452` "embeddings-only so it stays out"); the
rhodochrosite proxy routes `/v1/embeddings` generically but advertises no
embeddings model. **Zero indexers consume a free embedding route.**

1. **Catalog**: add `bge-m3` embeddings capability to the freeinference provider
   def in `mimetite/src/data.ts` (keep OUT of staticModels/chat seeds; emit as
   embeddings-only). Regenerate models.yml (mimetite, never hand-edit).
2. **Live-probe**: `POST /v1/embeddings {"model":"bge-m3","input":[...]}` vs the
   freeinference key — capture status, dims, response shape (DECLARED≠OBSERVED).
   Record token accounting + latency.
3. **Router**: advertise bge-m3 on rhodochrosite :25193 `/v1/embeddings` and
   add it to the freeinference overlay so a request resolves upstream.
4. **Indexer map**: FFS, BM25 (dualspace-ast-bm25), codebase-memory,
   estate-skills-hub (nemotron-retrieval-recipes embed.md),
   qdrant — document which accept an external embeddings provider.
5. **Shared embed client**: a single `embed()` (bge-m3 via freeinference) used
   by any indexer that takes a provider. Free, quota-safe (quotaSource :25109).
6. **Wire at least one real indexer end-to-end** as the show-problem (qdrant or
   codebase-memory), then generalize.
7. **Docs**: update `nemotron-retrieval-recipes/references/embed.md` to add the
   bge-m3 free path; note the MODEL-IDENTITY-CHAIN implications.

Steps 1 & 2 are the reviewable first unit; I hold this lane.
