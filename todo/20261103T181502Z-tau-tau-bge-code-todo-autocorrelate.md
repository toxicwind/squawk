# bge auto-correlate: code ↔ fleet todos

## The ask
Use the estate's free, unlimited bge-m3 lane to AUTO-CORRELATE code surfaces
to fleet todos — when a new todo lands, surface the repo files it most likely
touches (and vice versa: when a file changes, surface open todos it affects).

## Why now (evidence, 2026-11-03)
- freeinference bge-m3 verified unlimited/free ~99.9% (estate doctrine 2026-11-02)
- The concurrent-batch short-answer race is FIXED in tau 4b6a7eae19 + omp-wtf ce9ff9b — serial embeds + full-answer invariant + 1 retry; the lane is now reliable enough to serve an always-on correlator
- qdrant :25133 embed-cache pattern proven (cold 33s → warm 2.5s, sha256→UUID keys)
- The fleet board has 21 items, mostly un-parsed titles — no mapping from todo→code exists today
- tau-wtf carryback already computes fix↔tree similarity — the same instrument, pointed at todos

## Shape
1. `pens/ranch/squawk/mcp` or a small estate daemon: embed every open todo (title+body) into qdrant collection `fleet_todo_vectors`
2. Embed touched files' signatures (reuse wtf fileSignature) into `fleet_code_vectors`
3. Correlate on: todo-create (webhook/file-watch), todo-done, and on-demand `GET /correlate?file=<path>` / `?todo=<slug>`
4. Emit top-3 file↔todo matches per event to kafka estate.events + squawk #fleet card
5. Short-answer race contract: SERIAL embeds, full-answer invariant, 1 retry — per 4b6a7eae19

## Owner: tau
