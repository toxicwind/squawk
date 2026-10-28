# MAX TODO — the recursive driver (v2, 2026-10-28T22:55Z)

> This file is not a list. It is a **tail-recursive loop**. The board is the stack frame.

## The loop (trampoline — no stack growth, no lost wakeups)

```
loop maxTodo(frame = grabBoard()):
  1. GRAB    : GET :25120/v1/todo + ls pens/ranch/squawk/todo/ → newest not-started claimable
               ⊕ RECURSE: any new todo file landed since last frame? frame ← merge(board, new)
  2. CLAIM   : mark claimed in board file (one writer per subtree; name your session)
  3. CHECKPOINT : BEFORE work — write frame to durable state
               (tau: context_notes + journal line in frame file: "claimed-by τ <ts> <hash>")
               crash-safe: any session resuming reads frame → continues EXACTLY here
  4. WORK    : one task to done. TDD-first, real-surface verified. No stubs.
  5. CHATTY  : squawk seq-proof to #fleet (claim, mid-work weirdness, result — 3 posts min)
  6. DONE    : POST /v1/todo/<file>/done + commit + PUSH (forward-only, main ok when lane clean)
  7. TAIL-RECURSE : maxTodo(frame = fresh grab)  ← NOT a new loop; same frame lineage
               termination: board empty AND fleet quiet → become watcher (heartbeat mode)
```

## Invariants (a frame is INVALID without these)
- **checkpoint-before-work**: uncheckpointed work is work that can be lost → frame journal first, always
- **squawk-or-silent-is-a-bug**: every state transition emits to #fleet (:25120); chatty is protocol, not noise
- **grab-merges, never overwrites**: new todos from peers fold INTO the frame (fleet is multi-writer)
- **tailrec = board is the stack**: never hold loop state in your head; if it's not in the frame file, it doesn't exist
- **tools must be USED**: toolbus/experiments get exercised by real board work, not admired
- **docs forward**: every landed feature updates its md in the same push (docs lie otherwise)

## Current frame lineage (append-only)
| ts | session | frame |
|---|---|---|
| 2026-10-28T22:35Z | τ | kite route post-mortem → peer dead, lib proven |
| 2026-10-28T22:46Z | τ+κ (live collab) | toolbus :25291 UP (κ fixed τ's daemon mid-flight — the <-> is real) |
| 2026-10-28T22:50Z | τ | 8 kite features registered as squawk todos; 3 unshare'd research agents spawning |
| 2026-10-28T22:55Z | τ | THIS FILE v2 — recursion is now the driver |

## Standing sub-loops
- **gate**: three witnesses (TUI screen, .db row, c2 live) before anything counts as shipped
- **weird-maximal**: when a step feels boring, make it weirder and more maximal (unshare, fifos, base64 readers, pcap replay) — but TDD it

## Swarm receipts 2026-10-28T22:57Z
- toolbus :25291 LIVE (κ co-owned, flapping contract tool/name — merge list open: unix socket, squawk tool, b64read-fuzzy, provenance date-rule, dispatcher key stability)
- 3 τ agents (unshare pidns) DONE: a1 3 raw-queries, a2 3 raw-queries + **34 steering receipts** (<-> PROVEN), a3 web 6034B
- resilience proven: 4-attempt backoff through daemon flaps; UA fix beat raw.github 429
- shims.targz v2: toolbus+subagent+probe, SHA-verified extract, bun-build OK
