# Squawk paging + compaction — production results (Pry, 2026-10-19)

**Deliverable:** `squawk_page.py` (this dir; mirrored to yote
`/home/toxic/kite/pry-20261019-paging/` with race.py, eval_hybrid.py,
probes_archive.json). Stdlib-only, runs on yote against the live channel
store. Two surfaces:

- `page` — cursor-paged history. Cursor = envelope identity
  **(seq, filename)** (804 fleet seqs are shared by distinct messages;
  seq alone is not a key). Verified live: page 1 (limit 3) → page 2 via
  `next_before` disjoint + contiguous; pages stable under appends.
- `pack` — hybrid v2 context pack (below). ~11ms per build on the live
  16,305-msg fleet corpus; index pickle rebuilds on file-count change.

## Hybrid v2 (adopted production packer)

Two stages: **age-blind candidate retrieval** (top-200 pure TF-IDF
relevance ∪ top-100 surprise×relevance ∪ episode first/last anchors),
then ranking inside the candidate set: 0.55 relevance + 0.25 markov
surprise (sender×topic transitions, C3) + 0.20 importance (C1 proxies),
recency demoted to a 0.05 tiebreak. Episode-digest header ≤ budget/4
keeps unpacked spans addressable by seq range. Raw store never mutated.

## Eval — 11 probes (race 8 + 3 archive-era, all hand-verified)

Archive probes added to de-bias the race's today-skew (probes_archive.json):
A1 Oct 5 terminal-MCP forks (wezterm 41 / kitty 40 tools), A2 Oct 4
roundup sweep weights → sovereign router, A3 Oct 3 marquee README audit.

| packer | @4k | @16k |
|---|---|---|
| race C0 recency (reference) | 0/8* | 6/8* |
| race C1 / C3 (reference, 8 probes) | 7/8 · 6/8 | 7/8 · 8/8 |
| hybrid v1 (recency as full axis) | 7/11 | 7/11 |
| hybrid v1 + recency floor 0.30 | 7/11 | 8/11 |
| **hybrid v2 (production)** | **9/11** | **11/11** |

*race numbers on the original 8 probes only.

v1's failure was structural: with a 3-day half-life, a 2-week-old
message's recency axis is ~0.04, so age zeroed every archive hit no
matter the relevance. Floors only patched one probe. Making candidate
retrieval age-blind and demoting recency to a tiebreak fixed the class.

## Known limits / next experiments (not tuned against this probe set)

- v2 @4k misses Q3/Q5 (fresh probes v1's recency axis flattered).
  Candidate fix: budget-adaptive decay weight — needs FRESH probes to
  validate, not this set (overfit risk).
- Probe phrasing still couples to fleet register; real user queries
  will be messier. A query-log-based probe set is the honest next eval.
- Paging covers the file store; a JetStream-native page source (same
  cursor contract) is the follow-on for consumers that read the stream.

## Landing note

Ranch integration (a `ranch/squawk` home + pitchfork service) is held:
ranch is in Sable's preserved-but-not-applied reconcile state under
Chris's stop-and-report (2026-10-19 15:38). The tool runs standalone
from the yote mirror today; landing it in ranch is a follow-on once
Chris says go on the reconcile.
