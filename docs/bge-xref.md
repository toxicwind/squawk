# bge-xref — fleet todo ↔ Pens code cross-reference

Point an agent at the files its todo most likely touches. Two-stage hybrid
(Pens doctrine — same pattern as tau's LSP semanticRank): **BM25 recall**
from argos `pens-corpus` → **bge-m3 re-rank** of the candidates by meaning →
top-N real file paths stamped into the todo as a `touches:` footer.

```
bun bin/bge-xref.ts            # all open board todos
bun bin/bge-xref.ts --todo <f> # one todo
bun bin/bge-xref.ts --force    # re-stamp (replaces the footer, once)
bun bin/bge-xref.ts --top 10   # N hits (default 5)
```

## Module map

| Module | Seam | Borrowed from |
|---|---|---|
| `src/bge-xref/argos.ts` | ES-wire `_search` client (`multi_match`, ax_path→realPath) | tau-wtf audit.ts |
| `src/bge-xref/embed.ts` | serial full-answer embed lane + qdrant text cache | tau lsp/semantic.ts `embedFull` (4b6a7eae19), tau-wtf carryback embedCached |
| `src/bge-xref/rerank.ts` | cosine re-rank + skill-hub mirror dedupe | tau lsp/semantic.ts |
| `src/bge-xref/stamp.ts` | atomic `touches:` footer (tmp+rename, `run=` ids) | — |
| `src/bge-xref/lock.ts` | per-todo O_EXCL lock — single-stamp guarantee | squawk b8eb9ef |
| `src/bge-xref/todos.ts` | board discovery (SSOT = `ranch/squawk/todo`) | squawk bun/index.ts todoDir |
| `src/bge-xref/index.ts` | orchestration + CLI | — |

## Contracts (measured, 2026-11-03)

- **Never parallel embed batches**: freeinference answers a concurrent-batch
  loser with HTTP 200 + `{data:[]}` — serial + full-answer invariant + 1 retry.
- **Never stamp twice**: the whole read→recall→rank→stamp cycle runs under an
  O_EXCL per-todo lock; a crashed holder is stolen after 60s.
- **Cache-friendly**: identical texts are sha256→UUID-addressed in qdrant
  (`text_vectors`, 1024-dim), so repeated runs cost ~0 embeds.
- **argos recall is `multi_match`, never `query_string`** (the wire parser
  returns 0 hits even on sanitized input).
- **Board SSOT is `ranch/squawk/todo`** — `products/squawk/todo/` is a stale
  91-file remnant; never write board files there.